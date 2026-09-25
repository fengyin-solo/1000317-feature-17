"""组件清洗接口：维护清洗任务，覆盖确认排期、开始清洗、取消任务等动作。"""
from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.cleaning import cleaning_service

router = APIRouter(prefix="/api/cleaning", tags=["组件清洗"])

LIST_FIELDS = ["任务编号", "清洗区域", "计划日期", "实际完成日", "用水量", "作业班组", "清洗方式", "任务状态"]
STATUSES = ["待排期", "已排期", "清洗中", "已完成", "已取消"]
MONTH_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def _check_month(month: str | None) -> str | None:
    if month is not None and not MONTH_PATTERN.match(month):
        raise HTTPException(status_code=400, detail="月份格式应为 YYYY-MM，例如 2026-09")
    return month


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按任务编号检索"),
    status: str | None = Query(default=None, description="待排期、已排期、清洗中、已完成、已取消"),
    area: str | None = Query(default=None, description="按清洗区域筛选"),
    team: str | None = Query(default=None, description="按作业班组筛选"),
    month: str | None = Query(default=None, description="按计划日期所在月份筛选，格式 YYYY-MM"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按任务编号、状态、清洗区域、作业班组与月份过滤；超期任务自动排到最前。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    _check_month(month)
    items, total = cleaning_service.list_entries(
        keyword=keyword, status=status, area=area, team=team, month=month, page=page, size=size
    )
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/stats")
def get_stats(
    area: str | None = Query(default=None, description="按清洗区域筛选"),
    team: str | None = Query(default=None, description="按作业班组筛选"),
    month: str | None = Query(default=None, description="用水量统计月份，格式 YYYY-MM"),
) -> dict[str, Any]:
    """统计卡片：待排期清洗、清洗中任务、本月用水量，动作执行后重新拉取即可更新。"""
    _check_month(month)
    stats = cleaning_service.stats(area=area, team=team, month=month)
    return {"module": "cleaning", **stats}


@router.get("/export")
def export_entries(
    keyword: str | None = None,
    status: str | None = None,
    area: str | None = None,
    team: str | None = None,
    month: str | None = None,
) -> dict[str, Any]:
    """导出组件清洗清单：返回当前过滤条件下的全量数据（含超期/缺完成日标记）。"""
    _check_month(month)
    items, total = cleaning_service.list_entries(
        keyword=keyword, status=status, area=area, team=team, month=month, page=1, size=10000
    )
    return {"module": "cleaning", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条清洗任务明细；不存在时给出可读的错误说明。"""
    entry = cleaning_service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"清洗任务 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条清洗任务，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = cleaning_service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="清洗任务已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条清洗任务执行确认排期、开始清洗、取消任务；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = cleaning_service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
