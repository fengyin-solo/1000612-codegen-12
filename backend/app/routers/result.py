"""检测结果接口：维护检测结果，覆盖录入结果、提交复核、确认结果等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.result import ResultService

router = APIRouter(prefix="/api/result", tags=["检测结果"])

service = ResultService()

LIST_FIELDS = ["结果编号", "关联任务", "检测项目", "检测值", "计量单位", "检出限", "判定上限", "判定结论", "录入人员", "结果状态"]
STATUSES = ["待录入", "已录入", "待复核", "已确认"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按结果编号检索"),
    task: str | None = Query(default=None, alias="关联任务", description="按关联任务检索"),
    value: str | None = Query(default=None, alias="检测值", description="按检测值检索"),
    status: str | None = Query(default=None, description="待录入、已录入、待复核、已确认"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按结果编号、关联任务、检测值与状态过滤检测结果列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, task=task, value=value, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/stats")
def result_stats() -> dict[str, Any]:
    """统计卡片：待录入、待复核与不合格（超出上限）结果数，与结果列表同源。"""
    return {"module": "result", "items": service.stats()}


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出检测结果清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "result", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条检测结果明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"检测结果 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条检测结果：检测值格式、计量单位、结果编号任一校验不过都会拦下并说明原因。"""
    entry, errors = service.create_entry(payload.values)
    if errors:
        return ActionResult(ok=False, message="；".join(errors))
    return ActionResult(ok=True, message=f"检测结果已登记，判定结论：{entry['判定结论']}", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条检测结果执行录入结果、提交复核、确认结果；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
