"""DeepSeek analysis router."""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models.document import AnalysisResult, Document
from schemas.analysis import AnalysisResponse, AnalyzeRequest
from schemas.document import AnalysisResultOut
from services.deepseek_service import get_deepseek_service
from services.analysis_template_service import decode_fields, get_template_for_analysis

router = APIRouter(prefix="/api/analysis", tags=["analysis"])
logger = logging.getLogger("contract_analyzer.analysis")


@router.post("/{doc_id}/analyze", response_model=AnalysisResponse)
def analyze_document(doc_id: str, data: AnalyzeRequest | None = None, db: Session = Depends(get_db)):
    """Run DeepSeek analysis on an OCR-processed document."""
    document = db.query(Document).filter(Document.id == doc_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="文档不存在")
    if document.status != "ocr_done" and document.status != "done":
        raise HTTPException(
            status_code=400,
            detail=f"当前文档状态({document.status})不允许此操作，请先完成OCR识别",
        )
    if not document.ocr_text:
        raise HTTPException(status_code=400, detail="文档OCR文本为空，无法分析")

    template = get_template_for_analysis(db, data.template_id if data else None)
    if not template:
        raise HTTPException(status_code=404, detail="分析方案不存在，请先在设置中创建方案")

    had_results = db.query(AnalysisResult).filter(AnalysisResult.document_id == document.id).count() > 0

    try:
        document.status = "analyzing"
        document.error_message = None
        db.commit()

        deepseek = get_deepseek_service()
        results = deepseek.analyze_document(document, template)
        fields_snapshot = [
            field for field in decode_fields(template) if field.get("enabled", True)
        ]
        fields_snapshot_json = json.dumps(fields_snapshot, ensure_ascii=False)

        db.query(AnalysisResult).filter(
            AnalysisResult.document_id == document.id
        ).delete(synchronize_session=False)
        for result_data in results:
            ar = AnalysisResult(
                document_id=document.id,
                prompt_type=result_data["prompt_type"],
                prompt_text=result_data["prompt_text"],
                response_text=result_data["response_text"],
                tokens_used=result_data.get("tokens_used"),
                template_id=template.id,
                template_name=template.name,
                template_version=template.version,
                fields_snapshot_json=fields_snapshot_json,
            )
            db.add(ar)

        document.analysis_template_id = template.id
        document.analysis_template_name = template.name
        document.analysis_template_version = template.version
        document.status = "done"
        db.commit()
        stored_results = db.query(AnalysisResult).filter(
            AnalysisResult.document_id == document.id
        ).order_by(AnalysisResult.created_at.desc()).all()
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
                fields_snapshot=json.loads(r.fields_snapshot_json) if r.fields_snapshot_json else None,
                created_at=r.created_at.isoformat() if r.created_at else None,
            )
            for r in stored_results
        ]
        return AnalysisResponse(
            document_id=document.id,
            status=document.status,
            results=result_outs,
        )
    except Exception as exc:
        logger.exception("AI analysis failed document_id=%s", doc_id)
        db.rollback()
        document = db.query(Document).filter(Document.id == doc_id).first()
        document.status = "done" if had_results else "error"
        document.error_message = str(exc)
        db.commit()
        raise HTTPException(status_code=500, detail="AI分析失败，请稍后重试") from exc
