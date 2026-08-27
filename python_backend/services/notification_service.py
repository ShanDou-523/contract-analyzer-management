"""Idempotent reminder scanning for fulfillment-task in-app notifications."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import or_
from sqlalchemy.orm import Session

from core.security import as_utc
from models.contract import Contract, FulfillmentTask, Notification, User

ACTIVE_TASK_STATUSES = ("pending", "in_progress")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ReminderScanResult:
    examined_tasks: int
    created: int
    skipped_existing: int
    skipped_without_recipient: int


def _dedupe_key(
    task_id: str,
    recipient_id: str,
    notification_type: str,
    source_at: datetime,
) -> str:
    normalized = as_utc(source_at)
    value = f"{task_id}|{recipient_id}|{notification_type}|{normalized.isoformat()}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _active_recipient(
    task: FulfillmentTask,
    users: dict[str, User],
) -> User | None:
    if task.assignee_id and task.assignee_id in users:
        return users[task.assignee_id]
    return users.get(task.created_by)


def scan_fulfillment_reminders(
    db: Session,
    organization_id: str,
    *,
    now: datetime | None = None,
) -> ReminderScanResult:
    """Create due reminder records without delivering through an external channel."""
    scan_at = as_utc(now or now_utc())
    rows = (
        db.query(FulfillmentTask, Contract)
        .join(Contract, Contract.id == FulfillmentTask.contract_id)
        .filter(
            FulfillmentTask.organization_id == organization_id,
            FulfillmentTask.status.in_(ACTIVE_TASK_STATUSES),
            Contract.organization_id == organization_id,
            Contract.deleted_at.is_(None),
            or_(
                FulfillmentTask.remind_at <= scan_at,
                FulfillmentTask.due_at <= scan_at,
            ),
        )
        .all()
    )
    user_ids = {
        user_id
        for task, _contract in rows
        for user_id in (task.assignee_id, task.created_by)
        if user_id
    }
    users = {
        user.id: user
        for user in db.query(User)
        .filter(
            User.id.in_(user_ids),
            User.organization_id == organization_id,
            User.status == "active",
        )
        .all()
    }

    candidates: list[tuple[FulfillmentTask, Contract, User, str, datetime]] = []
    skipped_without_recipient = 0
    for task, contract in rows:
        recipient = _active_recipient(task, users)
        if recipient is None:
            skipped_without_recipient += 1
            continue
        remind_at = as_utc(task.remind_at)
        due_at = as_utc(task.due_at)
        if remind_at is not None and remind_at <= scan_at:
            candidates.append((task, contract, recipient, "reminder", remind_at))
        if due_at is not None and due_at <= scan_at:
            candidates.append((task, contract, recipient, "overdue", due_at))

    keyed_candidates = [
        (
            task,
            contract,
            recipient,
            notification_type,
            source_at,
            _dedupe_key(task.id, recipient.id, notification_type, source_at),
        )
        for task, contract, recipient, notification_type, source_at in candidates
    ]
    candidate_keys = [item[5] for item in keyed_candidates]
    existing_keys = {
        key
        for (key,) in db.query(Notification.dedupe_key)
        .filter(Notification.dedupe_key.in_(candidate_keys))
        .all()
    }

    created = 0
    for task, contract, recipient, notification_type, source_at, dedupe_key in keyed_candidates:
        if dedupe_key in existing_keys:
            continue
        is_overdue = notification_type == "overdue"
        db.add(
            Notification(
                organization_id=organization_id,
                recipient_id=recipient.id,
                contract_id=contract.id,
                task_id=task.id,
                notification_type=notification_type,
                status="unread",
                title=f"{'任务已逾期' if is_overdue else '履约任务提醒'}：{task.title}",
                message=(
                    f"合同“{contract.name}”的履约任务“{task.title}”"
                    f"{'已超过截止时间' if is_overdue else '已到提醒时间'}。"
                ),
                source_at=source_at,
                dedupe_key=dedupe_key,
                metadata_json=json.dumps(
                    {
                        "contract_no": contract.contract_no,
                        "due_at": as_utc(task.due_at).isoformat(),
                        "remind_at": as_utc(task.remind_at).isoformat() if task.remind_at else None,
                    },
                    ensure_ascii=False,
                ),
                generated_at=scan_at,
            )
        )
        existing_keys.add(dedupe_key)
        created += 1
    db.flush()
    return ReminderScanResult(
        examined_tasks=len(rows),
        created=created,
        skipped_existing=len(keyed_candidates) - created,
        skipped_without_recipient=skipped_without_recipient,
    )
