"""Validation and state-machine helpers for contract fulfillment tasks."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from core.security import as_utc
from models.contract import FulfillmentTask, User

TASK_TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset({"in_progress", "cancelled"}),
    "in_progress": frozenset({"pending", "completed", "cancelled"}),
    "completed": frozenset(),
    "cancelled": frozenset({"pending"}),
}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def validate_schedule(
    due_at: datetime,
    remind_at: datetime | None,
    *,
    allow_past_due: bool = False,
) -> tuple[datetime, datetime | None]:
    due = as_utc(due_at)
    remind = as_utc(remind_at)
    if due is None:
        raise HTTPException(status_code=422, detail="必须填写截止时间")
    if not allow_past_due and due < now_utc():
        raise HTTPException(status_code=422, detail="截止时间不能早于当前时间")
    if remind and remind > due:
        raise HTTPException(status_code=422, detail="提醒时间不能晚于截止时间")
    return due, remind


def ensure_assignee(db: Session, organization_id: str, assignee_id: str | None) -> None:
    if assignee_id is None:
        return
    assignee = (
        db.query(User)
        .filter(
            User.id == assignee_id,
            User.organization_id == organization_id,
            User.status == "active",
        )
        .one_or_none()
    )
    if assignee is None:
        raise HTTPException(status_code=422, detail="负责人不存在或不属于当前组织")


def validate_transition(current: str, target: str) -> None:
    if target == current:
        return
    if target not in TASK_TRANSITIONS.get(current, frozenset()):
        raise HTTPException(status_code=409, detail=f"不允许从 {current} 变更为 {target}")


def task_is_overdue(task: FulfillmentTask) -> bool:
    return (
        task.status not in {"completed", "cancelled"}
        and as_utc(task.due_at) is not None
        and as_utc(task.due_at) < now_utc()
    )
