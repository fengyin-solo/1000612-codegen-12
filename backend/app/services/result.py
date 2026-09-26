"""检测结果业务规则：录入校验、自动判定与状态流转都收在这里。

录入拦截口径（任一不满足就拦下本次录入并说明原因）：
- 必填字段缺失；
- 结果编号与已有记录重复；
- 检测值不是合法的非负数值；
- 关联任务不存在，或计量单位与该项目档案不一致。
没有判定规则的项目不拦录入，但结论只允许标记为「待人工判定」。
"""
from __future__ import annotations

from typing import Any

from app.services import judge
from app.store import store

MODULE = "result"
REQUIRED_FIELDS = ["结果编号", "关联任务", "检测值", "计量单位"]
STATUS_ORDER = ["待录入", "已录入", "待复核", "已确认"]
ACTION_RULES = {"录入结果": "已录入", "提交复核": "待复核", "确认结果": "已确认", "人工判定": "待复核"}
# 每个动作只允许从指定状态发起，避免把已确认的结果再改回去。
ACTION_FROM = {
    "录入结果": {"待录入"},
    "提交复核": {"已录入"},
    "确认结果": {"待复核"},
    "人工判定": {"已录入"},
}
NEGATIVE_ACTIONS: list[str] = []


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _find_task(task_no: str) -> dict[str, Any] | None:
    for row in store.rows("task"):
        if _clean(row.get("任务编号")) == task_no:
            return row
    return None


def _find_project(project_name: str) -> dict[str, Any] | None:
    for row in store.rows("project"):
        if _clean(row.get("项目名称")) == project_name:
            return row
    return None


def _apply_verdict(entry: dict[str, Any], project_name: str, value_text: str) -> None:
    """按项目统一规则写入判定结论；没有规则的项目只标记待人工判定。"""
    rule = judge.get_rule(project_name)
    if rule is None:
        entry["判定结论"] = judge.PENDING_MANUAL
        entry["manual_required"] = True
        entry["检出限"] = None
        entry["判定上限"] = None
        return
    conclusion = judge.judge(judge.parse_number(value_text), rule)
    entry["判定结论"] = conclusion
    entry["manual_required"] = False
    entry["检出限"] = str(rule["detection_limit"])
    entry["判定上限"] = str(rule["upper_limit"])
    entry["abnormal"] = conclusion == judge.CONCLUSION_OVER_LIMIT


class ResultService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("结果编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def validate_entry(self, values: dict[str, Any], exclude_id: int | None = None) -> list[str]:
        """把录入拦检集中在一处：返回本次录入被拦下的全部原因。

        exclude_id 用于补录场景：占位记录补检测值时不把自己的编号算作重复。
        """
        errors: list[str] = []
        missing = [field for field in REQUIRED_FIELDS if not _clean(values.get(field))]
        if missing:
            errors.append(f"缺少必填字段：{'、'.join(missing)}")
        result_no = _clean(values.get("结果编号"))
        duplicated = any(
            _clean(row.get("结果编号")) == result_no and int(row.get("id", 0)) != (exclude_id or 0)
            for row in store.rows(MODULE)
        )
        if result_no and duplicated:
            errors.append(f"结果编号「{result_no}」已存在，本次录入被拦下")
        task_no = _clean(values.get("关联任务"))
        task = _find_task(task_no) if task_no else None
        if task_no and task is None:
            errors.append(f"关联任务「{task_no}」不存在，无法确定检测项目")
        project = _find_project(_clean(task.get("检测项目"))) if task else None
        if task and project is None:
            errors.append(f"任务「{task_no}」关联的检测项目「{_clean(task.get('检测项目'))}」未登记")
        value_text = _clean(values.get("检测值"))
        if value_text and judge.parse_number(value_text) is None:
            errors.append(f"检测值「{value_text}」格式不合法：只接受非负数值，未检出请填 0")
        unit = _clean(values.get("计量单位"))
        if project is not None and unit and unit != _clean(project.get("计量单位")):
            errors.append(
                f"计量单位「{unit}」与检测项目「{_clean(project.get('项目名称'))}」"
                f"登记的「{_clean(project.get('计量单位'))}」不匹配"
            )
        return errors

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        errors = self.validate_entry(values)
        if errors:
            return None, errors
        task = _find_task(_clean(values.get("关联任务")))
        project_name = _clean(task.get("检测项目"))
        rows = store.rows(MODULE)
        entry: dict[str, Any] = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry["结果编号"] = _clean(values.get("结果编号"))
        entry["关联任务"] = _clean(values.get("关联任务"))
        entry["检测项目"] = project_name
        entry["检测值"] = _clean(values.get("检测值"))
        entry["计量单位"] = _clean(values.get("计量单位"))
        entry["录入人员"] = _clean(values.get("录入人员")) or None
        _apply_verdict(entry, project_name, entry["检测值"])
        entry["status"] = "已录入"
        entry["pending"] = True
        entry.setdefault("abnormal", False)
        entry["结果状态"] = entry["status"]
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str, values: dict[str, Any] | None = None) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"检测结果 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于检测结果可执行范围"
        if entry.get("status") not in ACTION_FROM[action]:
            return None, f"当前状态「{entry.get('status')}」不允许执行「{action}」"
        if action == "录入结果":
            return self._fill_value(entry, values or {})
        if action == "人工判定":
            return self._manual_verdict(entry, values or {})
        target = ACTION_RULES[action]
        if action == "提交复核" and entry.get("判定结论") == judge.PENDING_MANUAL:
            return None, "该项目没有判定规则，请先执行「人工判定」填写结论，再提交复核"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["结果状态"] = target
        message = "检测结果已确认" if action == "确认结果" else f"检测结果已{action}"
        return entry, message

    def _fill_value(self, entry: dict[str, Any], values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        """给待录入的占位记录补录检测值；校验口径与登记时完全一致。"""
        merged = {
            "结果编号": entry.get("结果编号"),
            "关联任务": entry.get("关联任务"),
            "检测值": values.get("检测值"),
            "计量单位": values.get("计量单位"),
        }
        errors = self.validate_entry(merged, exclude_id=int(entry.get("id", 0)))
        if errors:
            return None, "；".join(errors)
        task = _find_task(_clean(entry.get("关联任务")))
        entry["检测项目"] = _clean(task.get("检测项目"))
        entry["检测值"] = _clean(values.get("检测值"))
        entry["计量单位"] = _clean(values.get("计量单位"))
        if _clean(values.get("录入人员")):
            entry["录入人员"] = _clean(values.get("录入人员"))
        _apply_verdict(entry, entry["检测项目"], entry["检测值"])
        entry["status"] = "已录入"
        entry["pending"] = True
        entry["结果状态"] = "已录入"
        return entry, "检测结果已录入，判定结论已按项目规则生成"

    def _manual_verdict(self, entry: dict[str, Any], values: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
        """没有判定规则的项目：结论只能由人工给出，系统不自动生成。"""
        if not entry.get("manual_required"):
            return None, "该项目已有统一判定规则，结论由系统自动生成，无需人工判定"
        conclusion = _clean(values.get("判定结论"))
        if not conclusion:
            return None, "人工判定必须填写判定结论，本次操作未生效"
        entry["判定结论"] = conclusion
        entry["manual_required"] = False
        entry["abnormal"] = conclusion == judge.CONCLUSION_OVER_LIMIT
        entry["status"] = "待复核"
        entry["pending"] = True
        entry["结果状态"] = "待复核"
        return entry, "人工判定结论已记录，结果进入待复核"

    def stats(self) -> list[dict[str, Any]]:
        """统计卡片与列表同源：刷新后卡片数字始终等于列表里对应记录的条数。"""
        rows = store.rows(MODULE)
        return [
            {"label": "待录入结果", "value": sum(1 for row in rows if row.get("status") == "待录入")},
            {"label": "待复核结果", "value": sum(1 for row in rows if row.get("status") == "待复核")},
            {"label": "超出上限结果", "value": sum(1 for row in rows if row.get("判定结论") == judge.CONCLUSION_OVER_LIMIT)},
            {"label": "待人工判定", "value": sum(1 for row in rows if row.get("判定结论") == judge.PENDING_MANUAL)},
        ]
