"""检测结果自动判定与录入拦截的回归测试。

运行方式：cd backend && .venv/bin/python -m unittest discover -s tests -v
"""
from __future__ import annotations

import unittest
from decimal import Decimal

from app.services import judge
from app.services.result import ResultService
from app.store import store

RULE = judge.JUDGE_RULES["铅(以Pb计)"]


class JudgeRuleTest(unittest.TestCase):
    """同一套规则必须覆盖未检出、低于检出限、合格、超出上限四种情形。"""

    def test_zero_value_is_not_detected(self) -> None:
        self.assertEqual(judge.judge(Decimal("0"), RULE), "未检出")

    def test_below_detection_limit(self) -> None:
        self.assertEqual(judge.judge(Decimal("0.01"), RULE), "低于检出限")

    def test_between_limit_and_upper_is_qualified(self) -> None:
        self.assertEqual(judge.judge(Decimal("0.05"), RULE), "合格")
        self.assertEqual(judge.judge(Decimal("0.2"), RULE), "合格")

    def test_over_upper_limit(self) -> None:
        self.assertEqual(judge.judge(Decimal("0.35"), RULE), "超出上限")

    def test_parse_number_rejects_illegal_format(self) -> None:
        for bad in ("abc", "-1", "1.2.3", "1e3", "", None):
            self.assertIsNone(judge.parse_number(bad))
        self.assertEqual(judge.parse_number(" 0.05 "), Decimal("0.05"))


class ResultEntryTest(unittest.TestCase):
    """录入拦截与自动判定：每个用例用独立结果编号，避免相互污染。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.service = ResultService()
        cls._seq = 9000

    def _next_no(self) -> str:
        type(self)._seq += 1
        return f"RESU-{type(self)._seq}"

    def _create(self, **overrides: object) -> tuple[dict | None, list[str]]:
        values = {
            "结果编号": self._next_no(),
            "关联任务": "TASK-0003",
            "检测值": "0.05",
            "计量单位": "mg/kg",
        }
        values.update(overrides)
        return self.service.create_entry(values)

    def test_auto_verdict_by_value(self) -> None:
        cases = [("0", "未检出"), ("0.01", "低于检出限"), ("0.05", "合格"), ("0.35", "超出上限")]
        for value, expected in cases:
            entry, errors = self._create(检测值=value)
            self.assertEqual(errors, [])
            self.assertEqual(entry["判定结论"], expected)
            self.assertEqual(entry["检测值"], value, "录入的检测值取值不能被改写")

    def test_same_project_same_rule_on_different_result_no(self) -> None:
        first, _ = self._create(关联任务="TASK-0003", 检测值="0.01")
        second, _ = self._create(关联任务="TASK-0004", 检测值="0.01")
        self.assertEqual(first["判定结论"], second["判定结论"])
        self.assertEqual(first["检出限"], second["检出限"])

    def test_block_illegal_value(self) -> None:
        entry, errors = self._create(检测值="abc")
        self.assertIsNone(entry)
        self.assertTrue(any("格式不合法" in reason for reason in errors))

    def test_block_unit_mismatch(self) -> None:
        entry, errors = self._create(计量单位="mg/L")
        self.assertIsNone(entry)
        self.assertTrue(any("不匹配" in reason for reason in errors))

    def test_block_duplicate_result_no(self) -> None:
        entry, errors = self._create(结果编号="RESU-0001")
        self.assertIsNone(entry)
        self.assertTrue(any("已存在" in reason for reason in errors))

    def test_project_without_rule_marks_pending_manual(self) -> None:
        entry, errors = self._create(关联任务="TASK-0007", 检测值="1", 计量单位="定性")
        self.assertEqual(errors, [])
        self.assertEqual(entry["判定结论"], "待人工判定")
        self.assertTrue(entry["manual_required"])
        # 没有规则的项目不允许走自动提交复核，必须先人工判定
        blocked, message = self.service.run_action(entry["id"], "提交复核")
        self.assertIsNone(blocked)
        self.assertIn("人工判定", message)
        done, _ = self.service.run_action(entry["id"], "人工判定", {"判定结论": "阴性"})
        self.assertEqual(done["判定结论"], "阴性")
        self.assertEqual(done["status"], "待复核")

    def test_fill_pending_entry_uses_same_validation(self) -> None:
        """待录入占位补录：编号查重不能误伤自己，非法检测值同样拦下。"""
        pending = next(row for row in store.rows("result") if row.get("status") == "待录入")
        blocked, message = self.service.run_action(pending["id"], "录入结果", {"检测值": "abc", "计量单位": "mg/kg"})
        self.assertIsNone(blocked)
        self.assertIn("格式不合法", message)
        filled, message = self.service.run_action(pending["id"], "录入结果", {"检测值": "0.01", "计量单位": "mg/kg"})
        self.assertIsNotNone(filled, message)
        self.assertEqual(filled["判定结论"], "低于检出限")
        self.assertEqual(filled["检测值"], "0.01")

    def test_confirmed_entry_is_locked(self) -> None:
        entry, _ = self._create()
        entry, _ = self.service.run_action(entry["id"], "提交复核")
        entry, _ = self.service.run_action(entry["id"], "确认结果")
        self.assertEqual(entry["status"], "已确认")
        blocked, message = self.service.run_action(entry["id"], "提交复核")
        self.assertIsNone(blocked)
        self.assertIn("不允许", message)
        again = store.find("result", entry["id"])
        self.assertEqual(again["检测值"], "0.05", "已确认结果的取值不能改变")

    def test_stats_match_list_conclusions(self) -> None:
        self._create(检测值="0.35")
        stats = {item["label"]: item["value"] for item in self.service.stats()}
        rows = store.rows("result")
        self.assertEqual(stats["超出上限结果"], sum(1 for row in rows if row.get("判定结论") == "超出上限"))
        self.assertEqual(stats["待人工判定"], sum(1 for row in rows if row.get("判定结论") == "待人工判定"))
        self.assertEqual(stats["待复核结果"], sum(1 for row in rows if row.get("status") == "待复核"))


if __name__ == "__main__":
    unittest.main()
