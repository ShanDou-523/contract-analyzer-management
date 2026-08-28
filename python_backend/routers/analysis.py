"""DeepSeek analysis router."""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from config import DEEPSEEK_MODEL
from core.security import CurrentPrincipal, get_current_principal, require_roles
from database import get_db
from models.contract import (
    AnalysisRun,
    AnalysisTemplateVersion,
    Contract,
    ContractFile,
    FileVersion,
)
from models.document import AnalysisResult, Document
from schemas.analysis import AnalysisResponse, AnalyzeRequest
from schemas.document import AnalysisResultOut
from services.analysis_template_service import decode_fields, get_template_for_analysis
from services.audit_service import record_audit
from services.deepseek_service import get_deepseek_service

router = APIRouter(
    prefix="/api/analysis", tags=["analysis"], dependencies=[Depends(get_current_principal)]
)
logger = logging.getLogger("contract_analyzer.analysis")


def _analysis_run_context(db: Session, document: Document, template, principal: CurrentPrincipal):
    contract = (
        db.query(Contract)
        .filter(
            Contract.legacy_document_id == document.id,
            Contract.organization_id == principal.organization_id,
            Contract.deleted_at.is_(None),
        )
        .one_or_none()
    )
    if contract is None:
        contract = Contract(
            organization_id=principal.organization_id,
            legacy_document_id=document.id,
            name=Path(document.original_filename).stem.strip() or "未命名合同",
            category=template.name,
            status="active" if document.status in {"ocr_done", "done"} else "draft",
            source="legacy",
            metadata_json=json.dumps(
                {
                    "legacy_document_id": document.id,
                    "legacy_original_filename": document.original_filename,
                    "created_during_analysis": True,
                },
                ensure_ascii=False,
            ),
            created_by=principal.user_id,
            updated_by=principal.user_id,
        )
        db.add(contract)
        db.flush()
        record_audit(
            db,
            "contract.created_from_document",
            organization_id=principal.organization_id,
            user_id=principal.user_id,
            resource_type="contract",
            resource_id=contract.id,
            details={"document_id": document.id},
        )
    file_version = (
        db.query(FileVersion)
        .join(ContractFile, ContractFile.id == FileVersion.contract_file_id)
        .filter(
            ContractFile.contract_id == contract.id,
            FileVersion.is_current.is_(True),
            FileVersion.deleted_at.is_(None),
        )
        .order_by(FileVersion.version_no.desc())
        .first()
    )
    if file_version is None:
        contract_file = (
            db.query(ContractFile)
            .filter(
                ContractFile.contract_id == contract.id,
                ContractFile.purpose == "original",
                ContractFile.deleted_at.is_(None),
            )
            .one_or_none()
        )
        if contract_file is None:
            contract_file = ContractFile(contract_id=contract.id, purpose="original")
            db.add(contract_file)
            db.flush()
        version_no = max((item.version_no for item in contract_file.versions), default=0) + 1
        file_version = FileVersion(
            contract_file_id=contract_file.id,
            version_no=version_no,
            original_filename=document.original_filename,
            storage_key=document.stored_filename,
            mime_type="application/pdf",
            size_bytes=document.file_size,
            page_count=document.page_count,
            uploaded_by=principal.user_id,
            is_current=True,
        )
        db.add(file_version)
        db.flush()
        contract_file.current_version_id = file_version.id
    template_version = (
        db.query(AnalysisTemplateVersion)
        .filter(
            AnalysisTemplateVersion.template_id == template.id,
            AnalysisTemplateVersion.version == template.version,
        )
        .one_or_none()
    )
    if template_version is None:
        template_version = AnalysisTemplateVersion(
            template_id=template.id,
            version=template.version,
            fields_json=template.fields_json or "[]",
            analysis_focus=template.analysis_focus or "",
            review_enabled=bool(template.review_enabled),
            review_instructions=template.review_instructions or "",
            model_name=DEEPSEEK_MODEL,
            prompt_version=f"template-v{template.version}",
            status="published",
            created_by=principal.user_id,
            published_at=datetime.now(timezone.utc),
        )
        db.add(template_version)
        db.flush()
    return contract, file_version, template_version


@router.post("/{doc_id}/analyze", response_model=AnalysisResponse)
def analyze_document(
    doc_id: str,
    data: AnalyzeRequest | None = None,
    db: Session = Depends(get_db),
    principal: CurrentPrincipal = Depends(
        require_roles("system_admin", "org_admin", "contract_manager", "reviewer")
    ),
):
    """Run DeepSeek analysis on an OCR-processed document."""
    query = db.query(Document).filter(Document.id == doc_id)
    if isinstance(principal, CurrentPrincipal):
        query = query.filter(Document.organization_id == principal.organization_id)
    document = query.first()
    if not document:
        raise HTTPException(status_code=404, detail="文档不存在")
    if document.status != "ocr_done" and document.status != "done":
        raise HTTPException(
            status_code=400,
            detail=f"当前文档状态({document.status})不允许此操作，请先完成OCR识别",
        )
    if not document.ocr_text:
        raise HTTPException(status_code=400, detail="文档OCR文本为空，无法分析")

    organization_id = principal.organization_id if isinstance(principal, CurrentPrincipal) else None
    template = get_template_for_analysis(db, data.template_id if data else None, organization_id)
    if not template:
        raise HTTPException(status_code=404, detail="分析方案不存在，请先在设置中创建方案")

    had_results = (
        db.query(AnalysisResult).filter(AnalysisResult.document_id == document.id).count() > 0
    )
    analysis_run = None

    try:
        document.status = "analyzing"
        document.error_message = None
        context = (
            _analysis_run_context(db, document, template, principal)
            if isinstance(principal, CurrentPrincipal)
            else None
        )
        if context:
            contract, file_version, template_version = context
            analysis_run = AnalysisRun(
                contract_id=contract.id,
                file_version_id=file_version.id if file_version else None,
                task_type="analysis",
                status="running",
                requested_by=principal.user_id,
                started_at=datetime.now(timezone.utc),
                provider_name="deepseek",
                model_name=DEEPSEEK_MODEL,
                prompt_version=f"template-v{template.version}",
                template_version_id=template_version.id if template_version else None,
                input_chars=len(document.ocr_text or ""),
            )
            db.add(analysis_run)
        db.commit()

        deepseek = get_deepseek_service()
        results = deepseek.analyze_document(document, template)
        fields_snapshot = [field for field in decode_fields(template) if field.get("enabled", True)]
        fields_snapshot_json = json.dumps(fields_snapshot, ensure_ascii=False)

        new_results = []
        for result_data in results:
            ar = AnalysisResult(
                document_id=document.id,
                prompt_type=result_data["prompt_type"],
                prompt_text=result_data["prompt_text"],
                response_text=result_data["response_text"],
                tokens_used=result_data.get("tokens_used"),
                analysis_run_id=analysis_run.id if analysis_run else None,
                template_id=template.id,
                template_name=template.name,
                template_version=template.version,
                fields_snapshot_json=fields_snapshot_json,
            )
            db.add(ar)
            new_results.append(ar)

        document.analysis_template_id = template.id
        document.analysis_template_name = template.name
        document.analysis_template_version = template.version
        document.status = "done"
        if analysis_run:
            analysis_run.status = "succeeded"
            analysis_run.finished_at = datetime.now(timezone.utc)
            analysis_run.output_tokens = sum(item.tokens_used or 0 for item in new_results) or None
            record_audit(
                db,
                "analysis.run_succeeded",
                organization_id=principal.organization_id,
                user_id=principal.user_id,
                resource_type="analysis_run",
                resource_id=analysis_run.id,
                details={"document_id": document.id, "contract_id": analysis_run.contract_id},
            )
        db.commit()
        result_outs = [
            AnalysisResultOut(
                id=r.id,
                document_id=r.document_id,
                prompt_type=r.prompt_type,
                prompt_text=r.prompt_text,
                response_text=r.response_text,
                tokens_used=r.tokens_used,
                template_id=r.template_id,
                template_name=r.template_name,
                template_version=r.template_version,
                fields_snapshot=json.loads(r.fields_snapshot_json)
                if r.fields_snapshot_json
                else None,
                created_at=r.created_at.isoformat() if r.created_at else None,
            )
            for r in new_results
        ]
        return AnalysisResponse(
            document_id=document.id,
            status=document.status,
            results=result_outs,
        )
    except Exception as exc:
        logger.exception("AI analysis failed document_id=%s", doc_id)
        db.rollback()
        recovery_query = db.query(Document).filter(Document.id == doc_id)
        if isinstance(principal, CurrentPrincipal):
            recovery_query = recovery_query.filter(
                Document.organization_id == principal.organization_id
            )
        document = recovery_query.first()
        document.status = "done" if had_results else "error"
        document.error_message = str(exc)
        if analysis_run:
            failed_run = db.get(AnalysisRun, analysis_run.id)
            if failed_run:
                failed_run.status = "failed"
                failed_run.finished_at = datetime.now(timezone.utc)
                failed_run.error_code = type(exc).__name__
                failed_run.error_message = str(exc)[:5000]
                record_audit(
                    db,
                    "analysis.run_failed",
                    organization_id=principal.organization_id,
                    user_id=principal.user_id,
                    resource_type="analysis_run",
                    resource_id=failed_run.id,
                    details={"document_id": document.id},
                )
        db.commit()
        raise HTTPException(status_code=500, detail="AI分析失败，请稍后重试") from exc
