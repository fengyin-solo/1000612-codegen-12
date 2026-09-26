"""检测结果业务规则：自动判定、录入校验与状态流转都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "result"
REQUIRED_FIELDS = ["结果编号", "关联任务", "检测值", "计量单位"]
STATUS_ORDER = ["待录入", "已录入", "待复核", "已确认"]
ACTION_RULES = {"录入结果": "已录入", "提交复核": "待复核", "确认结果": "已确认"}

# 判定结论取值：三种需要区分的情形 + 正常检出 + 无规则时的人工兜底
CONCLUSION_NOT_DETECTED = "未检出"
CONCLUSION_BELOW_LOD = "低于检出限"
CONCLUSION_DETECTED = "检出"
CONCLUSION_OVER_LIMIT = "超出上限"
CONCLUSION_MANUAL = "待人工判定"

# 检测值里允许出现的未检出写法；「<数值」这类截尾值也按未检出处理
NOT_DETECTED_MARKERS = {"未检出", "未检测", "nd", "n.d", "n.d.", "nd."}
CENSOR_PREFIXES = ("<", "＜")


def parse_detection_value(raw: Any) -> tuple[str, float | None]:
    """把检测值解析成（类型, 数值）：number / not_detected / invalid。"""
    text = str(raw or "").strip()
    if not text:
        return "invalid", None
    if text.lower() in NOT_DETECTED_MARKERS:
        return "not_detected", None
    for prefix in CENSOR_PREFIXES:
        if text.startswith(prefix):
            try:
                float(text[len(prefix):].strip())
            except ValueError:
                return "invalid", None
            return "not_detected", None
    try:
        return "number", float(text)
    except ValueError:
        return "invalid", None


def _parse_limit(raw: Any) -> float | None:
    try:
        return float(str(raw or "").strip())
    except (TypeError, ValueError):
        return None


def find_task(task_no: str) -> dict[str, Any] | None:
    for row in store.rows("task"):
        if str(row.get("任务编号", "")).strip() == task_no:
            return row
    return None


def find_project(task: dict[str, Any]) -> dict[str, Any] | None:
    key = str(task.get("检测项目", "")).strip()
    if not key:
        return None
    for row in store.rows("project"):
        if key in {str(row.get("项目编码", "")).strip(), str(row.get("项目名称", "")).strip()}:
            return row
    return None


def project_rule(project: dict[str, Any] | None) -> dict[str, Any] | None:
    """从检测项目提取判定规则：检出限与计量单位必备，判定上限可选。"""
    if project is None:
        return None
    lod = _parse_limit(project.get("检出限"))
    unit = str(project.get("计量单位", "")).strip()
    if lod is None or not unit:
        return None
    return {"检出限": lod, "计量单位": unit, "判定上限": _parse_limit(project.get("判定上限"))}


def determine(kind: str, number: float | None, rule: dict[str, Any] | None) -> str:
    """按检测值与检出限、判定上限的关系给出结论；没有判定规则时只能待人工判定。"""
    if rule is None:
        return CONCLUSION_MANUAL
    if kind == "not_detected":
        return CONCLUSION_NOT_DETECTED
    assert number is not None
    if number < rule["检出限"]:
        return CONCLUSION_BELOW_LOD
    upper = rule.get("判定上限")
    if upper is not None and number > upper:
        return CONCLUSION_OVER_LIMIT
    return CONCLUSION_DETECTED


class ResultService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        task: str | None = None,
        value: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("结果编号", ""))]
        if task:
            rows = [row for row in rows if task in str(row.get("关联任务", ""))]
        if value:
            rows = [row for row in rows if value in str(row.get("检测值", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def stats(self) -> list[dict[str, Any]]:
        """统计卡片与结果列表同源：刷新后两边口径一致。"""
        rows = store.rows(MODULE)
        return [
            {"label": "待录入结果", "value": sum(1 for row in rows if row.get("status") == "待录入")},
            {"label": "待复核结果", "value": sum(1 for row in rows if row.get("status") == "待复核")},
            {"label": "不合格结果数", "value": sum(1 for row in rows if row.get("判定结论") == CONCLUSION_OVER_LIMIT)},
        ]

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, [f"缺少必填字段：{'、'.join(missing)}"]

        rows = store.rows(MODULE)
        result_no = str(values["结果编号"]).strip()
        if any(str(row.get("结果编号", "")).strip() == result_no for row in rows):
            return None, [f"结果编号「{result_no}」已存在，本次录入被拦下"]

        task_no = str(values["关联任务"]).strip()
        task = find_task(task_no)
        if task is None:
            return None, [f"关联任务「{task_no}」不存在，无法确定检测项目与判定规则"]

        kind, number = parse_detection_value(values["检测值"])
        if kind == "invalid":
            return None, [f"检测值「{str(values['检测值']).strip()}」格式不合法：应为数值，或「未检出」「<数值」"]

        project = find_project(task)
        rule = project_rule(project)
        unit = str(values["计量单位"]).strip()
        if rule is not None and unit != rule["计量单位"]:
            project_name = str(project.get("项目名称", "")).strip() if project else ""
            return None, [f"计量单位「{unit}」与项目「{project_name}」要求的「{rule['计量单位']}」不匹配，本次录入被拦下"]

        conclusion = determine(kind, number, rule)

        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry["结果编号"] = result_no
        entry["关联任务"] = task_no
        entry["检测项目"] = str(project.get("项目名称", "")).strip() if project else str(task.get("检测项目", "")).strip()
        entry["检测值"] = str(values["检测值"]).strip()
        entry["计量单位"] = unit
        # 判定口径以项目规则为准并随结果留存快照：同一项目在不同结果编号上保持一致
        if rule is not None and project is not None:
            entry["检出限"] = str(project.get("检出限", "")).strip()
            entry["判定上限"] = str(project.get("判定上限", "")).strip()
        else:
            entry["检出限"] = values.get("检出限")
            entry["判定上限"] = values.get("判定上限")
        entry["判定结论"] = conclusion
        entry["录入人员"] = str(values.get("录入人员") or "").strip()
        entry["结果状态"] = STATUS_ORDER[0]
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = conclusion == CONCLUSION_OVER_LIMIT
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"检测结果 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于检测结果可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        # 状态流转只改状态：检测值、判定结论等已有取值保持不变
        entry["status"] = target
        entry["结果状态"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = entry.get("判定结论") == CONCLUSION_OVER_LIMIT
        return entry, f"检测结果已{action}"
