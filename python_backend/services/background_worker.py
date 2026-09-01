"""Persistent background worker and durable job executors."""

from __future__ import annotations

import logging
import socket
import threading
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session, sessionmaker

import database
from core.security import as_utc
from models.contract import (
    BackgroundJob,
    BatchImport,
    BatchImportItem,
    Notification,
    NotificationDelivery,
    Organization,
    User,
)
from services.audit_service import record_audit
from services.background_job_service import (
    claim_next_job,
    decode_json,
    enqueue_job,
    mark_job_failed,
    mark_job_succeeded,
    recover_stale_jobs,
)
from services.batch_processing_service import run_analysis as run_batch_analysis
from services.batch_processing_service import run_ocr as run_batch_ocr
from services.notification_provider import (
    NotificationProvider,
    default_provider_registry,
)
from services.risk_notification_service import scan_risk_reminders
from services.risk_snapshot_service import create_daily_snapshot

logger = logging.getLogger("contract_analyzer.background_worker")

JOB_RISK_REMINDER_SCAN = "risk_reminder_scan"
JOB_NOTIFICATION_DISPATCH = "notification_dispatch"
JOB_NOTIFICATION_DELIVERY = "notification_delivery"
JOB_RISK_SNAPSHOT = "risk_report_snapshot"
JOB_BATCH_OCR = "batch_document_ocr"
JOB_BATCH_ANALYSIS = "batch_document_analysis"
SUPPORTED_JOB_TYPES = {
    JOB_RISK_REMINDER_SCAN,
    JOB_NOTIFICATION_DISPATCH,
    JOB_NOTIFICATION_DELIVERY,
    JOB_RISK_SNAPSHOT,
    JOB_BATCH_OCR,
    JOB_BATCH_ANALYSIS,
}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


class JobExecutionError(RuntimeError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        delivery_id: str | None = None,
        batch_item_id: str | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.delivery_id = delivery_id
        self.batch_item_id = batch_item_id


def _ensure_delivery_job(
    db: Session,
    notification: Notification,
    *,
    provider_name: str,
    requested_by: str | None,
) -> bool:
    delivery = (
        db.query(NotificationDelivery)
        .filter(
            NotificationDelivery.organization_id == notification.organization_id,
            NotificationDelivery.notification_id == notification.id,
            NotificationDelivery.provider_name == provider_name,
        )
        .one_or_none()
    )
    if delivery is not None:
        return False
    delivery = NotificationDelivery(
        organization_id=notification.organization_id,
        notification_id=notification.id,
        provider_name=provider_name,
        channel=provider_name,
        status="queued",
        attempt_count=0,
        max_attempts=3,
    )
    db.add(delivery)
    db.flush()
    job_result = enqueue_job(
        db,
        organization_id=notification.organization_id,
        job_type=JOB_NOTIFICATION_DELIVERY,
        dedupe_key=f"notification-delivery:{notification.id}:{provider_name}",
        payload={
            "notification_id": notification.id,
            "delivery_id": delivery.id,
            "provider_name": provider_name,
        },
        requested_by=requested_by,
        priority=10,
        max_attempts=delivery.max_attempts,
    )
    delivery.background_job_id = job_result.job.id
    return True


def enqueue_pending_deliveries(
    db: Session,
    organization_id: str,
    *,
    provider_name: str,
    requested_by: str | None = None,
) -> int:
    existing_delivery = db.query(NotificationDelivery.notification_id).filter(
        NotificationDelivery.organization_id == organization_id,
        NotificationDelivery.provider_name == provider_name,
    )
    notifications = (
        db.query(Notification)
        .filter(
            Notification.organization_id == organization_id,
            ~Notification.id.in_(existing_delivery),
        )
        .order_by(Notification.generated_at.asc())
        .all()
    )
    return sum(
        _ensure_delivery_job(
            db,
            notification,
            provider_name=provider_name,
            requested_by=requested_by,
        )
        for notification in notifications
    )


def schedule_recurring_jobs(
    db: Session,
    *,
    now: datetime | None = None,
    provider_name: str = "fake",
) -> int:
    current = as_utc(now or now_utc())
    hour_bucket = current.strftime("%Y%m%d%H")
    day_bucket = current.date().isoformat()
    organizations = db.query(Organization).filter(Organization.status == "active").all()
    created = 0
    for organization in organizations:
        jobs = (
            (
                JOB_RISK_REMINDER_SCAN,
                f"scheduled:risk-reminder-scan:{organization.id}:{hour_bucket}",
                {"provider_name": provider_name},
                20,
            ),
            (
                JOB_NOTIFICATION_DISPATCH,
                f"scheduled:notification-dispatch:{organization.id}:{hour_bucket}",
                {"provider_name": provider_name},
                10,
            ),
            (
                JOB_RISK_SNAPSHOT,
                f"scheduled:risk-report-snapshot:{organization.id}:{day_bucket}",
                {"snapshot_date": day_bucket},
                0,
            ),
        )
        for job_type, dedupe_key, payload, priority in jobs:
            result = enqueue_job(
                db,
                organization_id=organization.id,
                job_type=job_type,
                dedupe_key=dedupe_key,
                payload=payload,
                priority=priority,
            )
            created += int(result.created)
    db.commit()
    return created


def _execute_risk_reminder_scan(db: Session, job: BackgroundJob, current: datetime) -> dict:
    payload = decode_json(job.payload_json)
    provider_name = str(payload.get("provider_name") or "fake")
    result = scan_risk_reminders(db, job.organization_id, now=current)
    delivery_jobs = enqueue_pending_deliveries(
        db,
        job.organization_id,
        provider_name=provider_name,
        requested_by=job.requested_by,
    )
    return {
        "examined_risks": result.examined_risks,
        "created_notifications": result.created,
        "skipped_existing": result.skipped_existing,
        "skipped_without_recipient": result.skipped_without_recipient,
        "delivery_jobs": delivery_jobs,
    }


def _execute_notification_dispatch(db: Session, job: BackgroundJob) -> dict:
    payload = decode_json(job.payload_json)
    provider_name = str(payload.get("provider_name") or "fake")
    created = enqueue_pending_deliveries(
        db,
        job.organization_id,
        provider_name=provider_name,
        requested_by=job.requested_by,
    )
    return {"delivery_jobs": created, "provider_name": provider_name}


def _execute_notification_delivery(
    db: Session,
    job: BackgroundJob,
    providers: dict[str, NotificationProvider],
    current: datetime,
) -> dict:
    payload = decode_json(job.payload_json)
    delivery_id = str(payload.get("delivery_id") or "")
    notification_id = str(payload.get("notification_id") or "")
    provider_name = str(payload.get("provider_name") or "fake")
    delivery = (
        db.query(NotificationDelivery)
        .filter(
            NotificationDelivery.id == delivery_id,
            NotificationDelivery.organization_id == job.organization_id,
            NotificationDelivery.notification_id == notification_id,
        )
        .one_or_none()
    )
    if delivery is None:
        raise JobExecutionError("DELIVERY_NOT_FOUND", "通知投递记录不存在")
    if delivery.status == "sent":
        return {
            "delivery_id": delivery.id,
            "provider_message_id": delivery.provider_message_id,
            "already_sent": True,
        }
    notification = (
        db.query(Notification)
        .filter(
            Notification.id == notification_id,
            Notification.organization_id == job.organization_id,
        )
        .one_or_none()
    )
    if notification is None:
        raise JobExecutionError(
            "NOTIFICATION_NOT_FOUND", "站内通知不存在", delivery_id=delivery.id
        )
    recipient = (
        db.query(User)
        .filter(
            User.id == notification.recipient_id,
            User.organization_id == job.organization_id,
            User.status == "active",
        )
        .one_or_none()
    )
    if recipient is None:
        raise JobExecutionError(
            "RECIPIENT_NOT_FOUND", "通知接收人不存在或已停用", delivery_id=delivery.id
        )
    provider = providers.get(provider_name)
    if provider is None:
        raise JobExecutionError(
            "PROVIDER_NOT_FOUND", f"通知 provider 未注册：{provider_name}", delivery_id=delivery.id
        )
    delivery.status = "delivering"
    delivery.attempt_count += 1
    delivery.last_error = None
    delivery.next_retry_at = None
    db.flush()
    try:
        result = provider.send(
            notification,
            recipient,
            idempotency_key=notification.dedupe_key,
        )
    except Exception as exc:
        delivery.last_error = str(exc)[:5000]
        raise JobExecutionError("PROVIDER_DELIVERY_FAILED", str(exc), delivery_id=delivery.id) from exc
    delivery.channel = result.channel
    delivery.status = "sent"
    delivery.provider_message_id = result.provider_message_id
    delivery.sent_at = current
    delivery.next_retry_at = None
    db.flush()
    return {
        "delivery_id": delivery.id,
        "provider_name": provider_name,
        "provider_message_id": result.provider_message_id,
    }


def _execute_risk_snapshot(db: Session, job: BackgroundJob, current: datetime) -> dict:
    payload = decode_json(job.payload_json)
    snapshot_date_value = payload.get("snapshot_date")
    try:
        snapshot_date = datetime.fromisoformat(str(snapshot_date_value)).date()
    except (TypeError, ValueError):
        snapshot_date = current.date()
    snapshot = create_daily_snapshot(
        db,
        job.organization_id,
        snapshot_date=snapshot_date,
        generated_at=current,
        source_job_id=job.id,
    )
    return {
        "snapshot_id": snapshot.id,
        "snapshot_date": snapshot.snapshot_date.isoformat(),
        "total": snapshot.total,
        "overdue": snapshot.overdue,
        "overdue_rate": float(snapshot.overdue_rate or 0),
    }


def _update_batch_summary(db: Session, item: BatchImport, current: datetime) -> None:
    items = db.query(BatchImportItem).filter(BatchImportItem.batch_id == item.id).all()
    total = len(items)
    completed = sum(row.status == "done" for row in items)
    failed = sum(row.status == "error" for row in items)
    active = total - completed - failed
    item.total_count = total
    item.completed_count = completed
    item.failed_count = failed
    item.progress = round(sum(row.progress for row in items) / total) if total else 100
    if active:
        item.status = "queued" if all(row.status == "queued" for row in items) else "running"
        item.started_at = item.started_at or current
        item.finished_at = None
    elif failed:
        item.status = "partial" if completed else "failed"
        item.finished_at = item.finished_at or current
    else:
        item.status = "completed"
        item.started_at = item.started_at or current
        item.finished_at = item.finished_at or current
    item.updated_at = current
    db.flush()


def _execute_batch_ocr(db: Session, job: BackgroundJob, current: datetime) -> dict:
    payload = decode_json(job.payload_json)
    item_id = str(payload.get("batch_item_id") or "")
    item = (
        db.query(BatchImportItem)
        .filter(BatchImportItem.id == item_id, BatchImportItem.organization_id == job.organization_id)
        .one_or_none()
    )
    if item is None or item.document_id is None:
        raise JobExecutionError("BATCH_ITEM_NOT_FOUND", "批量导入文件不存在", batch_item_id=item_id)
    from models.document import Document

    document = db.get(Document, item.document_id)
    if document is None or document.organization_id != job.organization_id:
        raise JobExecutionError("BATCH_DOCUMENT_NOT_FOUND", "批量导入文档不存在", batch_item_id=item.id)
    if document.status in {"ocr_done", "done"} and document.ocr_text:
        item.status, item.stage, item.progress = "ocr_done", "analysis", 50
    else:
        item.status, item.stage, item.progress = "ocr_processing", "ocr", 20
        _update_batch_summary(db, db.get(BatchImport, item.batch_id), current)
        try:
            run_batch_ocr(db, document)
        except Exception as exc:
            raise JobExecutionError("OCR_FAILED", str(exc), batch_item_id=item.id) from exc
        item.status, item.stage, item.progress = "ocr_done", "analysis", 50
    analysis_job = enqueue_job(
        db,
        organization_id=job.organization_id,
        job_type=JOB_BATCH_ANALYSIS,
        dedupe_key=f"batch:{JOB_BATCH_ANALYSIS}:{item.id}:{item.retry_count}",
        payload={"batch_item_id": item.id, "document_id": item.document_id},
        requested_by=job.requested_by,
        priority=10,
    )
    item.analysis_job_id = analysis_job.job.id
    batch = db.get(BatchImport, item.batch_id)
    _update_batch_summary(db, batch, current)
    return {"batch_item_id": item.id, "analysis_job_id": analysis_job.job.id, "page_count": document.page_count}


def _execute_batch_analysis(db: Session, job: BackgroundJob, current: datetime) -> dict:
    payload = decode_json(job.payload_json)
    item_id = str(payload.get("batch_item_id") or "")
    item = (
        db.query(BatchImportItem)
        .filter(BatchImportItem.id == item_id, BatchImportItem.organization_id == job.organization_id)
        .one_or_none()
    )
    if item is None or item.document_id is None:
        raise JobExecutionError("BATCH_ITEM_NOT_FOUND", "批量导入文件不存在", batch_item_id=item_id)
    from models.document import Document

    document = db.get(Document, item.document_id)
    if document is None or document.organization_id != job.organization_id:
        raise JobExecutionError("BATCH_DOCUMENT_NOT_FOUND", "批量导入文档不存在", batch_item_id=item.id)
    item.status, item.stage, item.progress = "analyzing", "analysis", 65
    batch = db.get(BatchImport, item.batch_id)
    _update_batch_summary(db, batch, current)
    try:
        results = run_batch_analysis(
            db,
            document,
            organization_id=job.organization_id,
            user_id=job.requested_by or batch.created_by,
            template_id=batch.template_id,
        )
    except Exception as exc:
        raise JobExecutionError("ANALYSIS_FAILED", str(exc), batch_item_id=item.id) from exc
    item.status, item.stage, item.progress = "done", "analysis", 100
    _update_batch_summary(db, batch, current)
    return {"batch_item_id": item.id, "result_count": len(results)}


def execute_job(
    db: Session,
    job: BackgroundJob,
    *,
    providers: dict[str, NotificationProvider],
    now: datetime | None = None,
) -> dict:
    current = as_utc(now or now_utc())
    if job.job_type == JOB_RISK_REMINDER_SCAN:
        return _execute_risk_reminder_scan(db, job, current)
    if job.job_type == JOB_NOTIFICATION_DISPATCH:
        return _execute_notification_dispatch(db, job)
    if job.job_type == JOB_NOTIFICATION_DELIVERY:
        return _execute_notification_delivery(db, job, providers, current)
    if job.job_type == JOB_RISK_SNAPSHOT:
        return _execute_risk_snapshot(db, job, current)
    if job.job_type == JOB_BATCH_OCR:
        return _execute_batch_ocr(db, job, current)
    if job.job_type == JOB_BATCH_ANALYSIS:
        return _execute_batch_analysis(db, job, current)
    raise JobExecutionError("UNSUPPORTED_JOB_TYPE", f"不支持的后台任务类型：{job.job_type}")


def _sync_delivery_failure(db: Session, error: JobExecutionError, job: BackgroundJob) -> None:
    if not error.delivery_id:
        return
    delivery = (
        db.query(NotificationDelivery)
        .filter(
            NotificationDelivery.id == error.delivery_id,
            NotificationDelivery.organization_id == job.organization_id,
        )
        .one_or_none()
    )
    if delivery is None:
        return
    delivery.last_error = str(error)[:5000]
    delivery.status = "failed" if job.status == "failed" else "queued"
    delivery.next_retry_at = None if job.status == "failed" else job.available_at


def _sync_batch_failure(db: Session, error: JobExecutionError, job: BackgroundJob) -> None:
    if not error.batch_item_id:
        return
    item = (
        db.query(BatchImportItem)
        .filter(
            BatchImportItem.id == error.batch_item_id,
            BatchImportItem.organization_id == job.organization_id,
        )
        .one_or_none()
    )
    if item is None:
        return
    item.error_code = error.code
    item.error_message = str(error)[:5000]
    item.status = "error" if job.status == "failed" else "queued"
    if job.status == "failed":
        item.progress = max(0, item.progress)
        from models.document import Document

        document = db.get(Document, item.document_id) if item.document_id else None
        if document:
            if job.job_type == JOB_BATCH_OCR:
                document.status = "error"
                document.error_message = str(error)[:5000]
            elif job.job_type == JOB_BATCH_ANALYSIS:
                document.status = "ocr_done"
                document.error_message = str(error)[:5000]
    batch = db.get(BatchImport, item.batch_id)
    if batch:
        _update_batch_summary(db, batch, as_utc(job.updated_at) or now_utc())


def process_one_job(
    session_factory: sessionmaker,
    *,
    providers: dict[str, NotificationProvider] | None = None,
    worker_id: str | None = None,
    now: datetime | None = None,
    lock_timeout_seconds: int = 300,
) -> BackgroundJob | None:
    current = as_utc(now or now_utc())
    worker_name = worker_id or f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"
    registry = providers or default_provider_registry()
    db = session_factory()
    try:
        recover_stale_jobs(db, now=current, lock_timeout_seconds=lock_timeout_seconds)
        db.commit()
        job = claim_next_job(db, worker_id=worker_name, now=current)
        if job is None:
            return None
        try:
            result = execute_job(db, job, providers=registry, now=current)
            mark_job_succeeded(db, job, result, now=current)
            record_audit(
                db,
                "background_job.succeeded",
                organization_id=job.organization_id,
                user_id=job.requested_by,
                resource_type="background_job",
                resource_id=job.id,
                details={"job_type": job.job_type, "attempts": job.attempts},
            )
            db.commit()
        except JobExecutionError as exc:
            mark_job_failed(
                db,
                job,
                error_code=exc.code,
                error_message=str(exc),
                now=current,
            )
            _sync_delivery_failure(db, exc, job)
            _sync_batch_failure(db, exc, job)
            record_audit(
                db,
                "background_job.retry_scheduled" if job.status == "queued" else "background_job.failed",
                organization_id=job.organization_id,
                user_id=job.requested_by,
                resource_type="background_job",
                resource_id=job.id,
                details={"job_type": job.job_type, "attempts": job.attempts, "error_code": exc.code},
            )
            db.commit()
        except Exception as exc:
            db.rollback()
            job = db.get(BackgroundJob, job.id)
            payload = decode_json(job.payload_json) if job else {}
            mark_job_failed(
                db,
                job,
                error_code="JOB_EXECUTION_FAILED",
                error_message=str(exc),
                now=current,
            )
            if job and payload.get("batch_item_id"):
                _sync_batch_failure(
                    db,
                    JobExecutionError(
                        "JOB_EXECUTION_FAILED",
                        str(exc),
                        batch_item_id=str(payload["batch_item_id"]),
                    ),
                    job,
                )
            db.commit()
            logger.exception("Background job %s failed", job.id)
        db.refresh(job)
        return job
    finally:
        db.close()


class BackgroundWorker:
    def __init__(
        self,
        *,
        session_factory: sessionmaker | None = None,
        poll_seconds: float = 2.0,
        lock_timeout_seconds: int = 300,
        provider_name: str = "fake",
        providers: dict[str, NotificationProvider] | None = None,
    ):
        self.session_factory = session_factory
        self.poll_seconds = poll_seconds
        self.lock_timeout_seconds = lock_timeout_seconds
        self.provider_name = provider_name
        self.providers = providers or default_provider_registry()
        self.worker_id = f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._schedule_bucket: str | None = None

    def _sessions(self) -> sessionmaker:
        return self.session_factory or database.SessionLocal

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self.run_forever,
            name="contract-analyzer-worker",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=max(5.0, self.poll_seconds + 1))

    def _schedule(self, current: datetime) -> None:
        bucket = current.strftime("%Y%m%d%H%M")
        if bucket == self._schedule_bucket:
            return
        db = self._sessions()()
        try:
            schedule_recurring_jobs(db, now=current, provider_name=self.provider_name)
            self._schedule_bucket = bucket
        except Exception:
            db.rollback()
            logger.exception("Failed to schedule recurring jobs")
        finally:
            db.close()

    def run_forever(self) -> None:
        logger.info("Background worker started id=%s", self.worker_id)
        while not self._stop.is_set():
            current = now_utc()
            self._schedule(current)
            try:
                processed = process_one_job(
                    self._sessions(),
                    providers=self.providers,
                    worker_id=self.worker_id,
                    now=current,
                    lock_timeout_seconds=self.lock_timeout_seconds,
                )
            except Exception:
                processed = None
                logger.exception("Background worker polling failed")
            if processed is None:
                self._stop.wait(self.poll_seconds)
        logger.info("Background worker stopped id=%s", self.worker_id)
