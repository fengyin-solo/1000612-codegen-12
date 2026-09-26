"""检测值自动判定口径。

同一检测项目的判定规则只在这里定义一份，任何结果编号上的判定都走这一份规则，
避免不同录入人按不同口径各写一套结论。真实落地时这里应换成数据库里的判定规则表。

三种需要区分的情形：
- 检测值为 0            -> 未检出
- 0 < 检测值 < 检出限   -> 低于检出限
- 检出限 <= 检测值 <= 上限 -> 合格
- 检测值 > 上限         -> 超出上限
没有配置规则的项目不在自动判定范围内，结论只能标记为「待人工判定」。
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

# 检测值只接受非负有限小数：整数或带小数点的数字，拒绝负数、科学计数法、空串等。
NUMBER_PATTERN = re.compile(r"^\d+(?:\.\d+)?$")

CONCLUSION_NOT_DETECTED = "未检出"
CONCLUSION_BELOW_LIMIT = "低于检出限"
CONCLUSION_QUALIFIED = "合格"
CONCLUSION_OVER_LIMIT = "超出上限"
PENDING_MANUAL = "待人工判定"

AUTO_CONCLUSIONS = (
    CONCLUSION_NOT_DETECTED,
    CONCLUSION_BELOW_LIMIT,
    CONCLUSION_QUALIFIED,
    CONCLUSION_OVER_LIMIT,
)

# 项目名称 -> 该项目在所有结果编号上统一使用的判定口径。
# 计量单位需与检测项目档案保持一致；检出限与上限是比较检测值的唯一基准。
JUDGE_RULES: dict[str, dict[str, Any]] = {
    "铅(以Pb计)": {"unit": "mg/kg", "detection_limit": Decimal("0.02"), "upper_limit": Decimal("0.2")},
    "镉(以Cd计)": {"unit": "mg/kg", "detection_limit": Decimal("0.002"), "upper_limit": Decimal("0.1")},
    "菌落总数": {"unit": "CFU/g", "detection_limit": Decimal("10"), "upper_limit": Decimal("100000")},
}


def parse_number(raw: Any) -> Decimal | None:
    """把录入的检测值解析成数值；格式不合法时返回 None，由调用方拦下录入。"""
    text = str(raw or "").strip()
    if not NUMBER_PATTERN.fullmatch(text):
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def get_rule(project_name: str) -> dict[str, Any] | None:
    """按检测项目取统一规则；没有规则的项目返回 None，只能走人工判定。"""
    return JUDGE_RULES.get(str(project_name or "").strip())


def judge(value: Decimal, rule: dict[str, Any]) -> str:
    """按检测值与检出限、上限的关系给出判定结论。"""
    detection_limit = rule["detection_limit"]
    upper_limit = rule["upper_limit"]
    if value == 0:
        return CONCLUSION_NOT_DETECTED
    if value < detection_limit:
        return CONCLUSION_BELOW_LIMIT
    if value <= upper_limit:
        return CONCLUSION_QUALIFIED
    return CONCLUSION_OVER_LIMIT


def rule_view() -> list[dict[str, str]]:
    """供前端展示统一口径：让录入人在提交前就能看到项目对应的检出限与上限。"""
    return [
        {
            "检测项目": name,
            "计量单位": str(rule["unit"]),
            "检出限": str(rule["detection_limit"]),
            "判定上限": str(rule["upper_limit"]),
        }
        for name, rule in JUDGE_RULES.items()
    ]
