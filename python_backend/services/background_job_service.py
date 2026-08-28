"""Durable job queue primitives with lease recovery and bounded retry."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.security import as_utc
from models.contract import BackgroundJob
from schemas.background_jobs import BackgroundJobOut

JOB_STATUSES = {"queued", "running", "succeeded", "failed", "cancelled"}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def decode_json(value: str | None) -> dict[str, Any]:
    try:
        decoded = json.loads(value or "{}")
    except (TypeError, ValueError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


@dataclass(frozen=True)
class EnqueueResult:
    job: BackgroundJob
    created: bool


def enqueue_job(
    db: Session,
    *,
    organization_id: str,
    job_type: str,
    dedupe_key: str,
    payload: dict[str, Any] | None = None,
    requested_by: str | None = None,
    priority: int = 0,
    max_attempts: int = 3,
    available_at: datetime | None = None,
) -> EnqueueResult:
    existing = (
        db.query(BackgroundJob).filter(BackgroundJob.dedupe_key == dedupe_key).one_or_none()
    )
    if existing is not None:
        return EnqueueResult(job=existing, created=False)
    job = BackgroundJob(
        organization_id=organization_id,
        job_type=job_type,
        status="queued",
        priority=priority,
        payload_json=json.dumps(payload or {}, ensure_ascii=False, default=str),
        result_json="{}",
        dedupe_key=dedupe_key,
        attempts=0,
        max_attempts=max_attempts,
        available_at=as_utc(available_at or now_utc()),
        requested_by=requested_by,
    )
    try:
        with db.begin_nested():
            db.add(job)
            db.flush()
        return EnqueueResult(job=job, created=True)
    except IntegrityError:
        existing = (
            db.query(BackgroundJob).filter(BackgroundJob.dedupe_key == dedupe_key).one_or_none()
        )
        if existing is None:
            raise
        return EnqueueResult(job=existing, created=False)


def recover_stale_jobs(
    db: Session,
    *,
    now: datetime | None = None,
    lock_timeout_seconds: int = 300,
) -> int:
    current = as_utc(now or now_utc())
    cutoff = current - timedelta(seconds=lock_timeout_seconds)
    stale = (
        db.query(BackgroundJob)
        .filter(BackgroundJob.status == "running", BackgroundJob.locked_at < cutoff)
        .all()
    )
    for job in stale:
        job.locked_at = None
        job.locked_by = None
        job.error_code = "STALE_LEASE"
        job.error_message = "后台任务租约超时，已自动恢复"
        if job.attempts >= job.max_attempts:
            job.status = "failed"
            job.finished_at = current
        else:
            job.status = "queued"
            job.available_at = current
    if stale:
        db.flush()
    return len(stale)


def claim_next_job(
    db: Session,
    *,
    worker_id: str,
    now: datetime | None = None,
) -> BackgroundJob | None:
    current = as_utc(now or now_utc())
    candidates = (
        db.query(BackgroundJob.id)
        .filter(BackgroundJob.status == "queued", BackgroundJob.available_at <= current)
        .order_by(
            BackgroundJob.priority.desc(),
            BackgroundJob.available_at.asc(),
            BackgroundJob.created_at.asc(),
        )
        .limit(20)
        .all()
    )
    for (job_id,) in candidates:
        updated = (
            db.query(BackgroundJob)
            .filter(
                BackgroundJob.id == job_id,
                BackgroundJob.status == "queued",
                BackgroundJob.available_at <= current,
            )
            .update(
                {
                    BackgroundJob.status: "running",
                    BackgroundJob.locked_at: current,
                    BackgroundJob.locked_by: worker_id,
                    BackgroundJob.started_at: current,
                    BackgroundJob.finished_at: None,
                    BackgroundJob.attempts: BackgroundJob.attempts + 1,
                    BackgroundJob.error_code: None,
                    BackgroundJob.error_message: None,
                    BackgroundJob.updated_at: current,
                },
                synchronize_session=False,
            )
        )
        if updated:
            db.commit()
            return db.get(BackgroundJob, job_id)
        db.rollback()
    return None


def mark_job_succeeded(
    db: Session,
    job: BackgroundJob,
    result: dict[str, Any] | None = None,
    *,
    now: datetime | None = None,
) -> None:
    current = as_utc(now or now_utc())
    job.status = "succeeded"
    job.result_json = json.dumps(result or {}, ensure_ascii=False, default=str)
    job.finished_at = current
    job.locked_at = None
    job.locked_by = None
    job.error_code = None
    job.error_message = None
    job.updated_at = current
    db.flush()


def mark_job_failed(
    db: Session,
    job: BackgroundJob,
    *,
    error_code: str,
    error_message: str,
    now: datetime | None = None,
) -> None:
    current = as_utc(now or now_utc())
    job.error_code = error_code[:100]
    job.error_message = error_message[:5000]
    job.locked_at = None
    job.locked_by = None
    job.updated_at = current
    if job.attempts >= job.max_attempts:
        job.status = "failed"
        job.finished_at = current
    else:
        delay_seconds = min(300, 5 * (2 ** max(0, job.attempts - 1)))
        job.status = "queued"
        job.available_at = current + timedelta(seconds=delay_seconds)
        job.finished_at = None
    db.flush()


def retry_failed_job(
    job: BackgroundJob,
    *,
    now: datetime | None = None,
) -> None:
    if job.status != "failed":
        raise HTTPException(status_code=409, detail="只有失败任务可以重试")
    current = as_utc(now or now_utc())
    job.status = "queued"
    job.attempts = 0
    job.available_at = current
    job.started_at = None
    job.finished_at = None
    job.locked_at = None
    job.locked_by = None
    job.error_code = None
    job.error_message = None
    job.updated_at = current


def job_out(job: BackgroundJob) -> BackgroundJobOut:
    return BackgroundJobOut(
        id=job.id,
        organization_id=job.organization_id,
        job_type=job.job_type,
        status=job.status,
        priority=job.priority,
        payload=decode_json(job.payload_json),
        result=decode_json(job.result_json),
        attempts=job.attempts,
        max_attempts=job.max_attempts,
        available_at=job.available_at,
        locked_at=job.locked_at,
        locked_by=job.locked_by,
        started_at=job.started_at,
        finished_at=job.finished_at,
        requested_by=job.requested_by,
        error_code=job.error_code,
        error_message=job.error_message,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )
