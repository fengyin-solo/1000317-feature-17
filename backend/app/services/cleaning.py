"""组件清洗业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.store import store

MODULE = "cleaning"
REQUIRED_FIELDS = ["任务编号", "清洗区域", "计划日期"]
STATUS_ORDER = ["待排期", "已排期", "清洗中", "已完成", "已取消"]
ACTION_RULES = {"确认排期": "已排期", "开始清洗": "清洗中", "取消任务": "已取消"}
NEGATIVE_ACTIONS = []
# 已终结的状态：超期判断与统计口径都不再把它们当作待办
CLOSED_STATUSES = {"已完成", "已取消"}


def _parse_date(value: Any) -> date | None:
    """把 2026-09-01 这类字符串解析成日期；解析不了返回 None，不抛错。"""
    try:
        return date.fromisoformat(str(value or "").strip())
    except ValueError:
        return None


def _serialize(row: dict[str, Any]) -> dict[str, Any]:
    """列表/明细统一走拷贝返回：任务状态列始终跟着 status 走，不留旧值。"""
    entry = dict(row)
    entry["任务状态"] = str(row.get("status") or "")
    return entry


class CleaningService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        area: str | None = None,
        team: str | None = None,
        month: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("任务编号", ""))]
        if area:
            rows = [row for row in rows if area in str(row.get("清洗区域", ""))]
        if team:
            rows = [row for row in rows if team in str(row.get("作业班组", ""))]
        if month:
            rows = [row for row in rows if str(row.get("计划日期", "")).startswith(month)]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        rows = sorted(rows, key=self._sort_key)
        total = len(rows)
        start = max(page - 1, 0) * size
        return [_serialize(row) for row in rows[start:start + size]], total

    @staticmethod
    def _sort_key(row: dict[str, Any]) -> tuple[bool, date, int]:
        plan = _parse_date(row.get("计划日期"))
        overdue = (
            plan is not None
            and plan < date.today()
            and row.get("status") not in CLOSED_STATUSES
        )
        # 计划日期超期且未完成的任务排最前，其余按计划日期升序；日期缺失的沉底
        return (not overdue, plan or date.max, int(row.get("id", 0)))

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        row = store.find(MODULE, entry_id)
        return _serialize(row) if row is not None else None

    def stats(self) -> list[dict[str, Any]]:
        """统计卡片口径：待排期只数状态为待排期的任务，已取消不进任何待办口径。"""
        rows = store.rows(MODULE)
        today = date.today()
        pending = sum(1 for row in rows if row.get("status") == "待排期")
        running = sum(1 for row in rows if row.get("status") == "清洗中")
        water = 0.0
        for row in rows:
            if row.get("status") == "已取消":
                continue
            plan = _parse_date(row.get("计划日期"))
            if plan is None or (plan.year, plan.month) != (today.year, today.month):
                continue
            try:
                water += float(row.get("用水量") or 0)
            except (TypeError, ValueError):
                continue
        water_value: float | int = int(water) if water == int(water) else round(water, 2)
        return [
            {"label": "待排期清洗", "value": pending},
            {"label": "清洗中任务", "value": running},
            {"label": "本月用水量", "value": water_value},
        ]

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return _serialize(entry), []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"清洗任务 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于组件清洗可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target not in CLOSED_STATUSES
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return _serialize(entry), f"清洗任务已{action}"
