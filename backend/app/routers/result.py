"""检测结果接口：维护检测结果，覆盖录入结果、提交复核、确认结果等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services import judge
from app.services.result import ResultService

router = APIRouter(prefix="/api/result", tags=["检测结果"])

service = ResultService()

LIST_FIELDS = ["结果编号", "关联任务", "检测项目", "检测值", "计量单位", "检出限", "判定上限", "判定结论", "录入人员", "结果状态"]
STATUSES = ["待录入", "已录入", "待复核", "已确认"]


@router.get("/stats")
def stat_cards() -> dict[str, Any]:
    """统计卡片与列表同源：刷新后判定结论与卡片数字保持一致。"""
    return {"items": service.stats()}


@router.get("/rules")
def judge_rules() -> dict[str, Any]:
    """各检测项目的统一判定口径；不在清单里的项目只能走人工判定。"""
    return {"items": judge.rule_view()}


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出检测结果清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "result", "total": total, "items": items}


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按结果编号检索"),
    status: str | None = Query(default=None, description="待录入、已录入、待复核、已确认"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按结果编号与状态过滤检测结果列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条检测结果明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"检测结果 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条检测结果；格式、单位或编号问题会拦下本次录入并说明原因。"""
    entry, errors = service.create_entry(payload.values)
    if errors:
        return ActionResult(ok=False, message="；".join(errors))
    if entry.get("manual_required"):
        return ActionResult(ok=True, message="检测结果已登记：该项目没有判定规则，结论已标记为待人工判定", entry=entry)
    return ActionResult(ok=True, message="检测结果已登记，判定结论已按项目规则生成", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条检测结果执行录入结果、提交复核、确认结果、人工判定；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action, payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
