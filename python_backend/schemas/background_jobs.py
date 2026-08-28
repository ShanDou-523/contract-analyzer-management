"""Schemas for durable background work and notification delivery monitoring."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

JobStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]
DeliveryStatus = Literal["queued", "delivering", "sent", "failed"]


class BackgroundJobOut(BaseModel):
    id: str
    organization_id: str
    job_type: str
    status: JobStatus
    priority: int
    payload: dict[str, Any]
    result: dict[str, Any]
    attempts: int
    max_attempts: int
    available_at: datetime
    locked_at: datetime | None = None
    locked_by: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    requested_by: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class PagedBackgroundJobs(BaseModel):
    items: list[BackgroundJobOut]
    total: int = Field(ge=0)
    page: int
    page_size: int


class NotificationDeliveryOut(BaseModel):
    id: str
    organization_id: str
    notification_id: str
    notification_title: str
    recipient_id: str
    recipient_name: str
    background_job_id: str | None = None
    provider_name: str
    channel: str
    status: DeliveryStatus
    attempt_count: int
    max_attempts: int
    last_error: str | None = None
    provider_message_id: str | None = None
    next_retry_at: datetime | None = None
    sent_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class PagedNotificationDeliveries(BaseModel):
    items: list[NotificationDeliveryOut]
    total: int = Field(ge=0)
    page: int
    page_size: int
