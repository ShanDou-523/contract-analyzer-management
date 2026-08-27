"""Schemas for fulfillment dashboards, task search, and in-app notifications."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from schemas.fulfillment import FulfillmentTaskOut, TaskPriority, TaskStatus

NotificationStatus = Literal["unread", "read", "ignored"]
NotificationType = Literal["reminder", "overdue"]


class FulfillmentTaskListItemOut(FulfillmentTaskOut):
    contract_name: str
    contract_no: str | None = None
    assignee_name: str | None = None


class PagedFulfillmentTasksOut(BaseModel):
    items: list[FulfillmentTaskListItemOut]
    total: int
    page: int
    page_size: int


class StatusCountOut(BaseModel):
    status: TaskStatus
    count: int


class PriorityCountOut(BaseModel):
    priority: TaskPriority
    count: int


class AssigneeWorkloadOut(BaseModel):
    assignee_id: str | None = None
    assignee_name: str
    open_count: int
    overdue_count: int


class FulfillmentDashboardOut(BaseModel):
    generated_at: datetime
    total_open: int
    pending: int
    in_progress: int
    overdue: int
    due_today: int
    due_next_7_days: int
    unassigned: int
    completed_last_30_days: int
    unread_notifications: int
    status_counts: list[StatusCountOut]
    priority_counts: list[PriorityCountOut]
    assignee_workloads: list[AssigneeWorkloadOut]
    upcoming_tasks: list[FulfillmentTaskListItemOut]


class ReminderScanOut(BaseModel):
    examined_tasks: int
    created: int
    skipped_existing: int
    skipped_without_recipient: int


class NotificationOut(BaseModel):
    id: str
    organization_id: str
    recipient_id: str
    contract_id: str
    contract_name: str
    contract_no: str | None = None
    task_id: str
    task_title: str
    notification_type: NotificationType
    status: NotificationStatus
    title: str
    message: str
    source_at: datetime
    generated_at: datetime
    read_at: datetime | None = None
    ignored_at: datetime | None = None


class PagedNotificationsOut(BaseModel):
    items: list[NotificationOut]
    total: int
    unread: int
    page: int
    page_size: int


class NotificationStatusUpdate(BaseModel):
    status: Literal["read", "ignored"]


class UnreadCountOut(BaseModel):
    count: int = Field(ge=0)


class MarkAllReadOut(BaseModel):
    updated: int = Field(ge=0)
