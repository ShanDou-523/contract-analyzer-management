"""Asynchronous batch PDF upload, OCR, analysis, and retry APIs."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

import config
from core.security import CurrentPrincipal, get_current_principal, require_roles
from database import get_db
from models.contract import BackgroundJob, BatchImport, BatchImportItem
from models.document import Document
from schemas.batch_imports import BatchImportOut, PagedBatchImports
from services.analysis_template_service import get_template_for_analysis
from services.audit_service import record_audit
from services.background_job_service import enqueue_job
from services.background_worker import JOB_BATCH_ANALYSIS, JOB_BATCH_OCR
from services.batch_processing_service import item_out

router = APIRouter(prefix="/api/v1", tags=["batch-imports"])
MANAGE_ROLES = ("system_admin", "org_admin", "contract_manager")
MAX_BATCH_FILES = 100


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _update_batch_summary(db: Session, batch: BatchImport, *, now: datetime | None = None) -> None:
    current = now or _now()
    items = db.query(BatchImportItem).filter(BatchImportItem.batch_id == batch.id).all()
    total = len(items)
    completed = sum(item.status == "done" for item in items)
    failed = sum(item.status == "error" for item in items)
    active = total - completed - failed
    progress = round(sum(item.progress for item in items) / total) if total else 100
    batch.total_count = total
    batch.completed_count = completed
    batch.failed_count = failed
    if active:
        batch.status = "queued" if all(item.status == "queued" for item in items) else "running"
        if batch.started_at is None and batch.status == "running":
            batch.started_at = current
        batch.finished_at = None
    elif failed:
        batch.status = "partial" if completed else "failed"
        batch.finished_at = batch.finished_at or current
    else:
        batch.status = "completed"
        batch.started_at = batch.started_at or current
        batch.finished_at = batch.finished_at or current
    batch.updated_at = current
    batch.progress = progress
    db.flush()


def _batch_progress(batch: BatchImport) -> int:
    return int(batch.progress or 0)


def _batch_out(batch: BatchImport) -> BatchImportOut:
    return BatchImportOut(
        id=batch.id,
        organization_id=batch.organization_id,
        created_by=batch.created_by,
        template_id=batch.template_id,
        status=batch.status,
        total_count=batch.total_count,
        completed_count=batch.completed_count,
        failed_count=batch.failed_count,
        progress=_batch_progress(batch),
        created_at=batch.created_at,
        started_at=batch.started_at,
        finished_at=batch.finished_at,
        updated_at=batch.updated_at,
        items=[item_out(item) for item in sorted(batch.items, key=lambda row: row.created_at)],
    )


def _get_batch(db: Session, principal: CurrentPrincipal, batch_id: str) -> BatchImport:
    batch = (
        db.query(BatchImport)
        .filter(
            BatchImport.id == batch_id,
            BatchImport.organization_id == principal.organization_id,
        )
        .one_or_none()
    )
    if batch is None:
        raise HTTPException(status_code=404, detail="批量导入不存在")
    return batch


def _enqueue_item_job(
    db: Session,
    item: BatchImportItem,
    *,
    job_type: str,
    requested_by: str,
) -> BackgroundJob:
    result = enqueue_job(
        db,
        organization_id=item.organization_id,
        job_type=job_type,
        dedupe_key=f"batch:{job_type}:{item.id}:{item.retry_count}",
        payload={"batch_item_id": item.id, "document_id": item.document_id},
        requested_by=requested_by,
        priority=15,
    )
    if job_type == JOB_BATCH_OCR:
        item.ocr_job_id = result.job.id
    else:
        item.analysis_job_id = result.job.id
    return result.job


@router.post("/batch-imports", response_model=BatchImportOut, status_code=202)
async def create_batch_import(
    files: list[UploadFile] = File(...),
    template_id: str | None = Form(default=None),
    principal: CurrentPrincipal = Depends(require_roles(*MANAGE_ROLES)),
    db: Session = Depends(get_db),
):
    if not files:
        raise HTTPException(status_code=400, detail="至少选择一个PDF文件")
    if len(files) > MAX_BATCH_FILES:
        raise HTTPException(status_code=400, detail=f"单批最多导入{MAX_BATCH_FILES}个文件")
    template = get_template_for_analysis(db, template_id, principal.organization_id)
    if template is None:
        raise HTTPException(status_code=404, detail="分析方案不存在，请先选择有效方案")

    batch = BatchImport(
        organization_id=principal.organization_id,
        created_by=principal.user_id,
        template_id=template.id,
        status="queued",
    )
    db.add(batch)
    db.flush()
    saved_paths: list[Path] = []
    seen_hashes: set[str] = set()
    try:
        for upload in files:
            filename = Path(upload.filename or "").name
            content = await upload.read(config.settings.max_file_size_bytes + 1)
            digest = hashlib.sha256(content).hexdigest()
            valid = True
            error_code = None
            error_message = None
            if not filename.lower().endswith(".pdf"):
                valid = False
                error_code = "UNSUPPORTED_FILE_TYPE"
                error_message = "仅支持PDF文件格式"
            elif not content:
                valid = False
                error_code = "EMPTY_FILE"
                error_message = "不能上传空文件"
            elif len(content) > config.settings.max_file_size_bytes:
                valid = False
                error_code = "FILE_TOO_LARGE"
                error_message = f"文件大小超过{config.settings.max_file_size_mb}MB限制"
            elif digest in seen_hashes:
                valid = False
                error_code = "DUPLICATE_IN_BATCH"
                error_message = "同一批次中存在重复文件"
            seen_hashes.add(digest)

            document = None
            if valid:
                document_id = str(uuid.uuid4())
                stored_filename = f"{document_id}.pdf"
                config.settings.resolved_upload_dir.mkdir(parents=True, exist_ok=True)
                path = config.settings.resolved_upload_dir / stored_filename
                path.write_bytes(content)
                saved_paths.append(path)
                document = Document(
                    id=document_id,
                    original_filename=filename,
                    stored_filename=stored_filename,
                    organization_id=principal.organization_id,
                    file_size=len(content),
                    status="uploaded",
                    analysis_template_id=template.id,
                    analysis_template_name=template.name,
                    analysis_template_version=template.version,
                )
                db.add(document)
                db.flush()

            item = BatchImportItem(
                batch_id=batch.id,
                organization_id=principal.organization_id,
                document_id=document.id if document else None,
                original_filename=filename or "未命名文件",
                file_size=len(content),
                sha256=digest,
                status="queued" if valid else "error",
                stage="ocr",
                progress=0,
                error_code=error_code,
                error_message=error_message,
            )
            db.add(item)
            db.flush()
            if valid:
                _enqueue_item_job(
                    db,
                    item,
                    job_type=JOB_BATCH_OCR,
                    requested_by=principal.user_id,
                )

        _update_batch_summary(db, batch)
        record_audit(
            db,
            "batch_import.created",
            organization_id=principal.organization_id,
            user_id=principal.user_id,
            resource_type="batch_import",
            resource_id=batch.id,
            details={"total_count": batch.total_count, "failed_count": batch.failed_count},
        )
        db.commit()
        db.refresh(batch)
        return _batch_out(batch)
    except Exception:
        db.rollback()
        for path in saved_paths:
            path.unlink(missing_ok=True)
        raise


@router.get("/batch-imports", response_model=PagedBatchImports)
def list_batch_imports(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None, pattern=r"^(queued|running|completed|partial|failed|cancelled)$"),
    principal: CurrentPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    query = db.query(BatchImport).filter(BatchImport.organization_id == principal.organization_id)
    if status:
        query = query.filter(BatchImport.status == status)
    total = query.count()
    batches = (
        query.order_by(BatchImport.created_at.desc(), BatchImport.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    for batch in batches:
        _update_batch_summary(db, batch)
    db.commit()
    return PagedBatchImports(
        items=[_batch_out(batch) for batch in batches], total=total, page=page, page_size=page_size
    )


@router.get("/batch-imports/{batch_id}", response_model=BatchImportOut)
def get_batch_import(
    batch_id: str,
    principal: CurrentPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    batch = _get_batch(db, principal, batch_id)
    _update_batch_summary(db, batch)
    db.commit()
    db.refresh(batch)
    return _batch_out(batch)


@router.post("/batch-imports/{batch_id}/items/{item_id}/retry", response_model=BatchImportOut)
def retry_batch_item(
    batch_id: str,
    item_id: str,
    principal: CurrentPrincipal = Depends(require_roles(*MANAGE_ROLES)),
    db: Session = Depends(get_db),
):
    batch = _get_batch(db, principal, batch_id)
    item = (
        db.query(BatchImportItem)
        .filter(BatchImportItem.id == item_id, BatchImportItem.batch_id == batch.id)
        .one_or_none()
    )
    if item is None:
        raise HTTPException(status_code=404, detail="批次文件不存在")
    if item.status != "error":
        raise HTTPException(status_code=409, detail="只有失败文件可以重试")
    if not item.document_id:
        raise HTTPException(status_code=409, detail="文件未成功上传，无法重试；请重新选择文件")
    document = db.get(Document, item.document_id)
    if document is None or document.organization_id != principal.organization_id:
        raise HTTPException(status_code=404, detail="批次文件对应文档不存在")
    item.retry_count += 1
    item.error_code = None
    item.error_message = None
    if document.ocr_text and document.status in {"ocr_done", "done"}:
        item.stage = "analysis"
        item.status = "ocr_done"
        item.progress = 50
        document.status = "ocr_done"
        _enqueue_item_job(db, item, job_type=JOB_BATCH_ANALYSIS, requested_by=principal.user_id)
    else:
        item.stage = "ocr"
        item.status = "queued"
        item.progress = 0
        document.status = "uploaded"
        document.error_message = None
        _enqueue_item_job(db, item, job_type=JOB_BATCH_OCR, requested_by=principal.user_id)
    _update_batch_summary(db, batch)
    record_audit(
        db,
        "batch_import.item_retried",
        organization_id=principal.organization_id,
        user_id=principal.user_id,
        resource_type="batch_import_item",
        resource_id=item.id,
        details={"batch_id": batch.id, "stage": item.stage},
    )
    db.commit()
    db.refresh(batch)
    return _batch_out(batch)


@router.post("/batch-imports/{batch_id}/retry-failed", response_model=BatchImportOut)
def retry_failed_batch_items(
    batch_id: str,
    principal: CurrentPrincipal = Depends(require_roles(*MANAGE_ROLES)),
    db: Session = Depends(get_db),
):
    batch = _get_batch(db, principal, batch_id)
    failed_items = (
        db.query(BatchImportItem)
        .filter(BatchImportItem.batch_id == batch.id, BatchImportItem.status == "error")
        .all()
    )
    retried = 0
    for item in failed_items:
        if not item.document_id:
            continue
        document = db.get(Document, item.document_id)
        if document is None or document.organization_id != principal.organization_id:
            continue
        item.retry_count += 1
        item.error_code = None
        item.error_message = None
        if document.ocr_text and document.status in {"ocr_done", "done"}:
            item.stage, item.status, item.progress = "analysis", "ocr_done", 50
            document.status = "ocr_done"
            _enqueue_item_job(db, item, job_type=JOB_BATCH_ANALYSIS, requested_by=principal.user_id)
        else:
            item.stage, item.status, item.progress = "ocr", "queued", 0
            document.status = "uploaded"
            document.error_message = None
            _enqueue_item_job(db, item, job_type=JOB_BATCH_OCR, requested_by=principal.user_id)
        retried += 1
    _update_batch_summary(db, batch)
    record_audit(
        db,
        "batch_import.failed_items_retried",
        organization_id=principal.organization_id,
        user_id=principal.user_id,
        resource_type="batch_import",
        resource_id=batch.id,
        details={"retried": retried},
    )
    db.commit()
    db.refresh(batch)
    return _batch_out(batch)
