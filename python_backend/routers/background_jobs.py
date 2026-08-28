"""Organization-scoped durable job and notification delivery APIs."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from config import settings
from core.security import CurrentPrincipal, get_current_principal, require_roles
from database import get_db
from models.contract import BackgroundJob, Notification, NotificationDelivery, User
from schemas.background_jobs import (
    BackgroundJobOut,
    NotificationDeliveryOut,
    PagedBackgroundJobs,
    PagedNotificationDeliveries,
)
from services.audit_service import record_audit
from services.background_job_service import enqueue_job, job_out, retry_failed_job
from services.background_worker import JOB_NOTIFICATION_DISPATCH

router = APIRouter(prefix="/api/v1", tags=["background-jobs"])
MANAGE_ROLES = ("system_admin", "org_admin", "contract_manager", "reviewer")


def _get_job(db: Session, principal: CurrentPrincipal, job_id: str) -> BackgroundJob:
    job = (
        db.query(BackgroundJob)
        .filter(
            BackgroundJob.id == job_id,
            BackgroundJob.organization_id == principal.organization_id,
        )
        .one_or_none()
    )
    if job is None:
        raise HTTPException(status_code=404, detail="后台任务不存在")
    return job


@router.get("/background-jobs", response_model=PagedBackgroundJobs)
def list_background_jobs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(
        default=None, pattern=r"^(queued|running|succeeded|failed|cancelled)$"
    ),
    job_type: str | None = Query(default=None, max_length=50),
    principal: CurrentPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    query = db.query(BackgroundJob).filter(
        BackgroundJob.organization_id == principal.organization_id
    )
    if status:
        query = query.filter(BackgroundJob.status == status)
    if job_type:
        query = query.filter(BackgroundJob.job_type == job_type)
    total = query.count()
    jobs = (
        query.order_by(BackgroundJob.created_at.desc(), BackgroundJob.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return PagedBackgroundJobs(
        items=[job_out(job) for job in jobs],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/background-jobs/{job_id}", response_model=BackgroundJobOut)
def get_background_job(
    job_id: str,
    principal: CurrentPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    return job_out(_get_job(db, principal, job_id))


@router.post("/background-jobs/{job_id}/retry", response_model=BackgroundJobOut)
def retry_background_job(
    job_id: str,
    principal: CurrentPrincipal = Depends(require_roles(*MANAGE_ROLES)),
    db: Session = Depends(get_db),
):
    job = _get_job(db, principal, job_id)
    retry_failed_job(job)
    record_audit(
        db,
        "background_job.retried",
        organization_id=principal.organization_id,
        user_id=principal.user_id,
        resource_type="background_job",
        resource_id=job.id,
        details={"job_type": job.job_type},
    )
    db.commit()
    db.refresh(job)
    return job_out(job)


@router.post("/notification-deliveries/dispatch", response_model=BackgroundJobOut, status_code=202)
def queue_notification_dispatch(
    principal: CurrentPrincipal = Depends(require_roles(*MANAGE_ROLES)),
    db: Session = Depends(get_db),
):
    result = enqueue_job(
        db,
        organization_id=principal.organization_id,
        job_type=JOB_NOTIFICATION_DISPATCH,
        dedupe_key=f"manual:notification-dispatch:{principal.organization_id}:{uuid.uuid4()}",
        payload={"provider_name": settings.notification_provider},
        requested_by=principal.user_id,
        priority=10,
    )
    record_audit(
        db,
        "notification.delivery_dispatch_queued",
        organization_id=principal.organization_id,
        user_id=principal.user_id,
        resource_type="background_job",
        resource_id=result.job.id,
    )
    db.commit()
    db.refresh(result.job)
    return job_out(result.job)


@router.get("/notification-deliveries", response_model=PagedNotificationDeliveries)
def list_notification_deliveries(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None, pattern=r"^(queued|delivering|sent|failed)$"),
    provider_name: str | None = Query(default=None, max_length=50),
    principal: CurrentPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    query = (
        db.query(NotificationDelivery, Notification, User)
        .join(Notification, Notification.id == NotificationDelivery.notification_id)
        .join(User, User.id == Notification.recipient_id)
        .filter(
            NotificationDelivery.organization_id == principal.organization_id,
            Notification.organization_id == principal.organization_id,
            User.organization_id == principal.organization_id,
        )
    )
    if status:
        query = query.filter(NotificationDelivery.status == status)
    if provider_name:
        query = query.filter(NotificationDelivery.provider_name == provider_name)
    total = query.count()
    rows = (
        query.order_by(NotificationDelivery.updated_at.desc(), NotificationDelivery.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return PagedNotificationDeliveries(
        items=[
            NotificationDeliveryOut(
                id=delivery.id,
                organization_id=delivery.organization_id,
                notification_id=delivery.notification_id,
                notification_title=notification.title,
                recipient_id=notification.recipient_id,
                recipient_name=user.display_name or user.username,
                background_job_id=delivery.background_job_id,
                provider_name=delivery.provider_name,
                channel=delivery.channel,
                status=delivery.status,
                attempt_count=delivery.attempt_count,
                max_attempts=delivery.max_attempts,
                last_error=delivery.last_error,
                provider_message_id=delivery.provider_message_id,
                next_retry_at=delivery.next_retry_at,
                sent_at=delivery.sent_at,
                created_at=delivery.created_at,
                updated_at=delivery.updated_at,
            )
            for delivery, notification, user in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )
