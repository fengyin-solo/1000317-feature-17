"""组件清洗业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from app.store import store

MODULE = "cleaning"
REQUIRED_FIELDS = ["任务编号", "清洗区域", "计划日期"]
STATUS_ORDER = ["待排期", "已排期", "清洗中", "已完成", "已取消"]
ACTION_RULES = {"确认排期": "已排期", "开始清洗": "清洗中", "取消任务": "已取消"}
NEGATIVE_ACTIONS = []
FINISHED_STATUSES = {"已完成", "已取消"}

DONE_FIELD = "实际完成日"
WATER_FIELD = "用水量"
PLAN_FIELD = "计划日期"


def _parse_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_water(value: Any) -> float:
    text = str(value or "").strip()
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def _annotate(row: dict[str, Any], overdue: bool) -> dict[str, Any]:
    """给列表行补两个展示标记：超期、实际完成日缺失；只标记，不剔除任何任务。"""
    item = dict(row)
    item["overdue"] = bool(overdue)
    item["missing_done"] = not str(row.get(DONE_FIELD) or "").strip()
    return item


class CleaningService:
    def _filtered_rows(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        area: str | None = None,
        team: str | None = None,
    ) -> list[dict[str, Any]]:
        rows = store.rows(MODULE)
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("任务编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        if area:
            rows = [row for row in rows if area in str(row.get("清洗区域", ""))]
        if team:
            rows = [row for row in rows if team in str(row.get("作业班组", ""))]
        return rows

    def _scope_rows(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        area: str | None = None,
        team: str | None = None,
        month: str | None = None,
    ) -> list[dict[str, Any]]:
        """统一口径：返回筛选+排序后的行（超期结转在前），列表与统计共用，保证数字对得上。"""
        rows = self._filtered_rows(keyword=keyword, status=status, area=area, team=team)

        if month:
            month_start = datetime.strptime(month, "%Y-%m").date().replace(day=1)
            carry, in_month = [], []
            for row in rows:
                plan = _parse_date(row.get(PLAN_FIELD))
                if plan is None:
                    # 计划日期缺失/无法解析的任务不能凭空消失，留在当月列表末尾。
                    in_month.append((row, plan))
                elif plan < month_start:
                    # 早于所选月份且未完结（未完成、未取消）的任务视为超期结转。
                    if row.get("status") not in FINISHED_STATUSES:
                        carry.append((row, plan))
                elif plan.year == month_start.year and plan.month == month_start.month:
                    in_month.append((row, plan))

            def sort_key(item: tuple[dict[str, Any], date | None]) -> Any:
                row, plan = item
                return (plan or date.max, str(row.get("任务编号", "")))

            # 超期任务按计划日期从早到晚排到最前面；已取消的不进超期口径。
            carry.sort(key=sort_key)
            in_month.sort(key=sort_key)
            return [row for row, _ in carry] + [row for row, _ in in_month]

        def fallback_key(row: dict[str, Any]) -> Any:
            return (_parse_date(row.get(PLAN_FIELD)) or date.max, str(row.get("任务编号", "")))

        return sorted(rows, key=fallback_key)

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        area: str | None = None,
        team: str | None = None,
        month: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = self._scope_rows(keyword=keyword, status=status, area=area, team=team, month=month)
        today = date.today()

        def is_overdue(row: dict[str, Any]) -> bool:
            if row.get("status") in FINISHED_STATUSES:
                return False
            plan = _parse_date(row.get(PLAN_FIELD))
            if month:
                month_start = datetime.strptime(month, "%Y-%m").date().replace(day=1)
                return plan is not None and plan < month_start
            return plan is not None and plan < today

        ordered = [_annotate(row, overdue=is_overdue(row)) for row in rows]
        total = len(ordered)
        start = max(page - 1, 0) * size
        return ordered[start:start + size], total

    def stats(
        self,
        *,
        area: str | None = None,
        team: str | None = None,
        month: str | None = None,
    ) -> dict[str, int | float]:
        """统计卡片与列表同口径：待排期只认「待排期」状态，取消/已排期都不计入。"""
        if month is None:
            month = date.today().strftime("%Y-%m")
        rows = self._scope_rows(area=area, team=team, month=month)
        pending = sum(1 for row in rows if row.get("status") == "待排期")
        cleaning = sum(1 for row in rows if row.get("status") == "清洗中")
        water = sum(_parse_water(row.get(WATER_FIELD)) for row in rows)
        return {
            "pending": pending,
            "cleaning": cleaning,
            "water": round(water, 1),
        }

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry[DONE_FIELD] = values.get(DONE_FIELD)
        entry[WATER_FIELD] = values.get(WATER_FIELD)
        entry["作业班组"] = values.get("作业班组")
        entry["清洗方式"] = values.get("清洗方式")
        entry["status"] = STATUS_ORDER[0]
        entry["任务状态"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

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
        entry["任务状态"] = target
        # 待排期口径只认「待排期」：取消后排期不再占用待排期数量，排期/开工也照旧。
        entry["pending"] = target == "待排期"
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"清洗任务已{action}"


cleaning_service = CleaningService()
