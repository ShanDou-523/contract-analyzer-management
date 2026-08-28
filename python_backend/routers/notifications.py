"""Organization-scoped fulfillment dashboard, task search, and notifications."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, or_
from sqlalchemy.orm import Session

from core.security import CurrentPrincipal, as_utc, get_current_principal, require_roles
from database import get_db
from models.contract import AnalysisRisk, Contract, FulfillmentTask, Notification, User
from schemas.fulfillment import FulfillmentTaskOut
from schemas.notifications import (
    AssigneeWorkloadOut,
    FulfillmentDashboardOut,
    FulfillmentTaskListItemOut,
    MarkAllReadOut,
    NotificationOut,
    NotificationStatusUpdate,
    PagedFulfillmentTasksOut,
    PagedNotificationsOut,
    PriorityCountOut,
    ReminderScanOut,
    StatusCountOut,
    UnreadCountOut,
)
from services import notification_service
from services.audit_service import record_audit
from services.fulfillment_service import task_is_overdue

router = APIRouter(prefix="/api/v1", tags=["notifications"])
MANAGE_ROLES = ("system_admin", "org_admin", "contract_manager")
ACTIVE_STATUSES = {"pending", "in_progress"}
TASK_STATUSES = ("pending", "in_progress", "completed", "cancelled")
TASK_PRIORITIES = ("low", "medium", "high", "critical")


def _task_list_item(
    task: FulfillmentTask,
    contract_name: str,
    contract_no: str | None,
    assignee_name: str | None,
) -> FulfillmentTaskListItemOut:
    payload = FulfillmentTaskOut.model_validate(task).model_dump()
    payload["is_overdue"] = task_is_overdue(task)
    return FulfillmentTaskListItemOut(
        **payload,
        contract_name=contract_name,
        contract_no=contract_no,
        assignee_name=assignee_name,
    )


def _notification_out(
    notification: Notification,
    contract: Contract,
    task: FulfillmentTask | None,
    risk: AnalysisRisk | None = None,
) -> NotificationOut:
    return NotificationOut(
        id=notification.id,
        organization_id=notification.organization_id,
        recipient_id=notification.recipient_id,
        contract_id=notification.contract_id,
        contract_name=contract.name,
        contract_no=contract.contract_no,
        task_id=notification.task_id,
        task_title=task.title if task else None,
        risk_id=notification.risk_id,
        risk_title=risk.title if risk else None,
        remediation_due_at=risk.remediation_due_at if risk else None,
        notification_type=notification.notification_type,
        status=notification.status,
        title=notification.title,
        message=notification.message,
        source_at=notification.source_at,
        generated_at=notification.generated_at,
        read_at=notification.read_at,
        ignored_at=notification.ignored_at,
    )


def _task_rows(db: Session, organization_id: str):
    return (
        db.query(FulfillmentTask, Contract)
        .join(Contract, Contract.id == FulfillmentTask.contract_id)
        .filter(
            FulfillmentTask.organization_id == organization_id,
            Contract.organization_id == organization_id,
            Contract.deleted_at.is_(None),
        )
        .all()
    )


def _user_names(db: Session, organization_id: str, user_ids: set[str]) -> dict[str, str]:
    if not user_ids:
        return {}
    return {
        user.id: user.display_name or user.username
        for user in db.query(User)
        .filter(User.organization_id == organization_id, User.id.in_(user_ids))
        .all()
    }


@router.post("/fulfillment/reminders/scan", response_model=ReminderScanOut)
def scan_reminders(
    principal: CurrentPrincipal = Depends(require_roles(*MANAGE_ROLES)),
    db: Session = Depends(get_db),
):
    result = notification_service.scan_fulfillment_reminders(
        db,
        principal.organization_id,
    )
    record_audit(
        db,
        "fulfillment.reminders_scanned",
        organization_id=principal.organization_id,
        user_id=principal.user_id,
        resource_type="fulfillment",
        details={
            "examined_tasks": result.examined_tasks,
            "created": result.created,
            "skipped_existing": result.skipped_existing,
            "skipped_without_recipient": result.skipped_without_recipient,
        },
    )
    db.commit()
    return ReminderScanOut(**result.__dict__)


@router.get("/fulfillment/tasks", response_model=PagedFulfillmentTasksOut)
def list_fulfillment_tasks(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None, max_length=200),
    status: str | None = Query(
        default=None,
        pattern=r"^(pending|in_progress|completed|cancelled)$",
    ),
    priority: str | None = Query(default=None, pattern=r"^(low|medium|high|critical)$"),
    assignee_id: str | None = Query(default=None, max_length=36),
    contract_id: str | None = Query(default=None, max_length=36),
    overdue_only: bool = False,
    due_from: datetime | None = None,
    due_to: datetime | None = None,
    sort_by: str = Query(default="due_at", pattern=r"^(due_at|created_at|title|priority)$"),
    sort_order: str = Query(default="asc", pattern=r"^(asc|desc)$"),
    principal: CurrentPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    query = (
        db.query(FulfillmentTask, Contract, User)
        .join(Contract, Contract.id == FulfillmentTask.contract_id)
        .outerjoin(
            User,
            (User.id == FulfillmentTask.assignee_id)
            & (User.organization_id == principal.organization_id),
        )
        .filter(
            FulfillmentTask.organization_id == principal.organization_id,
            Contract.organization_id == principal.organization_id,
            Contract.deleted_at.is_(None),
        )
    )
    if search and search.strip():
        term = search.strip()
        query = query.filter(
            or_(
                FulfillmentTask.title.contains(term, autoescape=True),
                Contract.name.contains(term, autoescape=True),
                Contract.contract_no.contains(term, autoescape=True),
            )
        )
    if status:
        query = query.filter(FulfillmentTask.status == status)
    if priority:
        query = query.filter(FulfillmentTask.priority == priority)
    if assignee_id == "unassigned":
        query = query.filter(FulfillmentTask.assignee_id.is_(None))
    elif assignee_id:
        query = query.filter(FulfillmentTask.assignee_id == assignee_id)
    if contract_id:
        query = query.filter(FulfillmentTask.contract_id == contract_id)
    if overdue_only:
        query = query.filter(
            FulfillmentTask.status.in_(ACTIVE_STATUSES),
            FulfillmentTask.due_at < notification_service.now_utc(),
        )
    if due_from:
        query = query.filter(FulfillmentTask.due_at >= as_utc(due_from))
    if due_to:
        query = query.filter(FulfillmentTask.due_at <= as_utc(due_to))

    total = query.count()
    priority_order = case(
        (FulfillmentTask.priority == "critical", 4),
        (FulfillmentTask.priority == "high", 3),
        (FulfillmentTask.priority == "medium", 2),
        else_=1,
    )
    sort_columns = {
        "due_at": FulfillmentTask.due_at,
        "created_at": FulfillmentTask.created_at,
        "title": FulfillmentTask.title,
        "priority": priority_order,
    }
    sort_column = sort_columns[sort_by]
    ordered = sort_column.desc() if sort_order == "desc" else sort_column.asc()
    rows = (
        query.order_by(ordered, FulfillmentTask.created_at.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return PagedFulfillmentTasksOut(
        items=[
            _task_list_item(
                task,
                contract.name,
                contract.contract_no,
                assignee.display_name or assignee.username if assignee else None,
            )
            for task, contract, assignee in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/fulfillment/dashboard", response_model=FulfillmentDashboardOut)
def fulfillment_dashboard(
    principal: CurrentPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    now = as_utc(notification_service.now_utc())
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = start_of_day + timedelta(days=1)
    seven_days = now + timedelta(days=7)
    thirty_days_ago = now - timedelta(days=30)
    rows = _task_rows(db, principal.organization_id)
    tasks = [task for task, _contract in rows]
    active = [task for task in tasks if task.status in ACTIVE_STATUSES]

    user_ids = {task.assignee_id for task in active if task.assignee_id}
    names = _user_names(db, principal.organization_id, user_ids)
    status_counts = Counter(task.status for task in tasks)
    priority_counts = Counter(task.priority for task in active)

    workloads: dict[str | None, dict[str, int]] = {}
    for task in active:
        counters = workloads.setdefault(task.assignee_id, {"open": 0, "overdue": 0})
        counters["open"] += 1
        if as_utc(task.due_at) < now:
            counters["overdue"] += 1
    workload_items = [
        AssigneeWorkloadOut(
            assignee_id=assignee_id,
            assignee_name=names.get(assignee_id, "未分配") if assignee_id else "未分配",
            open_count=counts["open"],
            overdue_count=counts["overdue"],
        )
        for assignee_id, counts in workloads.items()
    ]
    workload_items.sort(
        key=lambda item: (-item.overdue_count, -item.open_count, item.assignee_name)
    )

    upcoming_rows = sorted(
        (
            (task, contract)
            for task, contract in rows
            if task.status in ACTIVE_STATUSES and as_utc(task.due_at) >= now
        ),
        key=lambda item: as_utc(item[0].due_at),
    )[:10]
    unread = (
        db.query(Notification)
        .join(Contract, Contract.id == Notification.contract_id)
        .filter(
            Notification.organization_id == principal.organization_id,
            Notification.recipient_id == principal.user_id,
            Notification.status == "unread",
            Contract.organization_id == principal.organization_id,
            Contract.deleted_at.is_(None),
        )
        .count()
    )
    return FulfillmentDashboardOut(
        generated_at=now,
        total_open=len(active),
        pending=status_counts["pending"],
        in_progress=status_counts["in_progress"],
        overdue=sum(as_utc(task.due_at) < now for task in active),
        due_today=sum(start_of_day <= as_utc(task.due_at) < end_of_day for task in active),
        due_next_7_days=sum(now <= as_utc(task.due_at) <= seven_days for task in active),
        unassigned=sum(task.assignee_id is None for task in active),
        completed_last_30_days=sum(
            task.status == "completed"
            and task.completed_at is not None
            and as_utc(task.completed_at) >= thirty_days_ago
            for task in tasks
        ),
        unread_notifications=unread,
        status_counts=[
            StatusCountOut(status=status, count=status_counts[status]) for status in TASK_STATUSES
        ],
        priority_counts=[
            PriorityCountOut(priority=priority, count=priority_counts[priority])
            for priority in TASK_PRIORITIES
        ],
        assignee_workloads=workload_items,
        upcoming_tasks=[
            _task_list_item(
                task,
                contract.name,
                contract.contract_no,
                names.get(task.assignee_id) if task.assignee_id else None,
            )
            for task, contract in upcoming_rows
        ],
    )


def _notification_query(db: Session, principal: CurrentPrincipal):
    return (
        db.query(Notification, Contract, FulfillmentTask, AnalysisRisk)
        .join(Contract, Contract.id == Notification.contract_id)
        .outerjoin(FulfillmentTask, FulfillmentTask.id == Notification.task_id)
        .outerjoin(AnalysisRisk, AnalysisRisk.id == Notification.risk_id)
        .filter(
            Notification.organization_id == principal.organization_id,
            Notification.recipient_id == principal.user_id,
            Contract.organization_id == principal.organization_id,
            Contract.deleted_at.is_(None),
            or_(
                FulfillmentTask.id.is_(None),
                FulfillmentTask.organization_id == principal.organization_id,
            ),
            or_(
                AnalysisRisk.id.is_(None),
                AnalysisRisk.organization_id == principal.organization_id,
            ),
            or_(Notification.task_id.isnot(None), Notification.risk_id.isnot(None)),
        )
    )


@router.get("/notifications", response_model=PagedNotificationsOut)
def list_notifications(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None, pattern=r"^(unread|read|ignored)$"),
    notification_type: str | None = Query(default=None, pattern=r"^(reminder|overdue|risk_reminder|risk_overdue)$"),
    principal: CurrentPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    query = _notification_query(db, principal)
    unread = query.filter(Notification.status == "unread").count()
    if status:
        query = query.filter(Notification.status == status)
    if notification_type:
        query = query.filter(Notification.notification_type == notification_type)
    total = query.count()
    rows = (
        query.order_by(Notification.generated_at.desc(), Notification.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return PagedNotificationsOut(
        items=[
            _notification_out(notification, contract, task, risk)
            for notification, contract, task, risk in rows
        ],
        total=total,
        unread=unread,
        page=page,
        page_size=page_size,
    )


@router.get("/notifications/unread-count", response_model=UnreadCountOut)
def unread_notification_count(
    principal: CurrentPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    return UnreadCountOut(
        count=_notification_query(db, principal).filter(Notification.status == "unread").count()
    )


@router.patch("/notifications/{notification_id}", response_model=NotificationOut)
def update_notification_status(
    notification_id: str,
    data: NotificationStatusUpdate,
    principal: CurrentPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    row = (
        _notification_query(db, principal).filter(Notification.id == notification_id).one_or_none()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="通知不存在")
    notification, contract, task, risk = row
    now = notification_service.now_utc()
    notification.status = data.status
    notification.read_at = now if data.status == "read" else None
    notification.ignored_at = now if data.status == "ignored" else None
    record_audit(
        db,
        f"notification.{data.status}",
        organization_id=principal.organization_id,
        user_id=principal.user_id,
        resource_type="notification",
        resource_id=notification.id,
        details={
            "task_id": task.id if task else None,
            "risk_id": risk.id if risk else None,
            "contract_id": contract.id,
        },
    )
    db.commit()
    db.refresh(notification)
    return _notification_out(notification, contract, task, risk)


@router.post("/notifications/read-all", response_model=MarkAllReadOut)
def mark_all_notifications_read(
    principal: CurrentPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    rows = _notification_query(db, principal).filter(Notification.status == "unread").all()
    now = notification_service.now_utc()
    for notification, _contract, _task, _risk in rows:
        notification.status = "read"
        notification.read_at = now
        notification.ignored_at = None
    if rows:
        record_audit(
            db,
            "notification.read_all",
            organization_id=principal.organization_id,
            user_id=principal.user_id,
            resource_type="notification",
            details={"count": len(rows)},
        )
    db.commit()
    return MarkAllReadOut(updated=len(rows))
