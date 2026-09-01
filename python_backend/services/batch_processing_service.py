"""Reusable OCR and DeepSeek processing steps for batch workers."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from config import DEEPSEEK_MODEL
from core.security import CurrentPrincipal
from models.contract import AnalysisRun, BatchImportItem, User
from models.document import AnalysisResult, Document
from services.analysis_template_service import decode_fields, get_template_for_analysis
from services.audit_service import record_audit
from services.deepseek_service import get_deepseek_service
from services.ocr_service import get_ocr_service


def run_ocr(db: Session, document: Document) -> dict:
    """Run OCR and update the legacy document without committing the transaction."""
    document.status = "ocr_processing"
    document.error_message = None
    db.flush()
    result = get_ocr_service().extract_text_from_pdf(document.stored_filename)
    document.ocr_text = result["full_text"]
    document.page_count = result["page_count"]
    document.ocr_pages_detail = json.dumps(result["pages"], ensure_ascii=False)
    document.status = "ocr_done"
    document.error_message = None
    db.flush()
    return result


def run_analysis(
    db: Session,
    document: Document,
    *,
    organization_id: str,
    user_id: str,
    template_id: str | None,
) -> list[AnalysisResult]:
    """Run the existing analysis pipeline for a worker-owned batch item."""
    if document.status not in {"ocr_done", "done"} or not document.ocr_text:
        raise ValueError("文档尚未完成OCR，无法进行AI分析")

    template = get_template_for_analysis(db, template_id, organization_id)
    if not template:
        raise ValueError("分析方案不存在，请先选择有效方案")

    from routers.analysis import _analysis_run_context

    user = db.get(User, user_id)
    if user is None or user.organization_id != organization_id:
        raise ValueError("批量任务的操作用户不存在或组织不匹配")
    principal = CurrentPrincipal(user=user, roles=frozenset())
    had_results = db.query(AnalysisResult).filter(AnalysisResult.document_id == document.id).count() > 0
    document.status = "analyzing"
    document.error_message = None
    contract, file_version, template_version = _analysis_run_context(db, document, template, principal)
    analysis_run = AnalysisRun(
        contract_id=contract.id,
        file_version_id=file_version.id if file_version else None,
        task_type="analysis",
        status="running",
        requested_by=user_id,
        started_at=datetime.now(timezone.utc),
        provider_name="deepseek",
        model_name=DEEPSEEK_MODEL,
        prompt_version=f"template-v{template.version}",
        template_version_id=template_version.id if template_version else None,
        input_chars=len(document.ocr_text or ""),
    )
    db.add(analysis_run)
    db.flush()
    try:
        results = get_deepseek_service().analyze_document(document, template)
        fields_snapshot = [field for field in decode_fields(template) if field.get("enabled", True)]
        fields_snapshot_json = json.dumps(fields_snapshot, ensure_ascii=False)
        new_results = [
            AnalysisResult(
                document_id=document.id,
                prompt_type=result_data["prompt_type"],
                prompt_text=result_data["prompt_text"],
                response_text=result_data["response_text"],
                tokens_used=result_data.get("tokens_used"),
                analysis_run_id=analysis_run.id,
                template_id=template.id,
                template_name=template.name,
                template_version=template.version,
                fields_snapshot_json=fields_snapshot_json,
            )
            for result_data in results
        ]
        db.add_all(new_results)
        document.analysis_template_id = template.id
        document.analysis_template_name = template.name
        document.analysis_template_version = template.version
        document.status = "done"
        analysis_run.status = "succeeded"
        analysis_run.finished_at = datetime.now(timezone.utc)
        analysis_run.output_tokens = sum(item.tokens_used or 0 for item in new_results) or None
        record_audit(
            db,
            "analysis.run_succeeded",
            organization_id=organization_id,
            user_id=user_id,
            resource_type="analysis_run",
            resource_id=analysis_run.id,
            details={"document_id": document.id, "contract_id": contract.id, "batch": True},
        )
        db.flush()
        return new_results
    except Exception:
        document.status = "done" if had_results else "ocr_done"
        document.error_message = None
        analysis_run.status = "failed"
        analysis_run.finished_at = datetime.now(timezone.utc)
        raise


def item_out(item: BatchImportItem):
    from schemas.batch_imports import BatchImportItemOut

    return BatchImportItemOut(
        id=item.id,
        batch_id=item.batch_id,
        organization_id=item.organization_id,
        document_id=item.document_id,
        original_filename=item.original_filename,
        file_size=item.file_size,
        status=item.status,
        stage=item.stage,
        progress=item.progress,
        ocr_job_id=item.ocr_job_id,
        analysis_job_id=item.analysis_job_id,
        retry_count=item.retry_count,
        error_code=item.error_code,
        error_message=item.error_message,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )
