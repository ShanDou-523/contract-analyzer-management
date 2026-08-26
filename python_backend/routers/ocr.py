"""OCR processing router."""

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models.document import Document
from schemas.analysis import OcrProcessResponse
from services.ocr_service import get_ocr_service

router = APIRouter(prefix="/api/ocr", tags=["ocr"])
logger = logging.getLogger("contract_analyzer.ocr")


@router.post("/{doc_id}/process", response_model=OcrProcessResponse)
def process_ocr(doc_id: str, db: Session = Depends(get_db)):
    """Run OCR on an uploaded document."""
    document = db.query(Document).filter(Document.id == doc_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="文档不存在")
    if document.status != "uploaded":
        raise HTTPException(
            status_code=400,
            detail=f"当前文档状态({document.status})不允许此操作，请先上传文档",
        )

    try:
        document.status = "ocr_processing"
        document.error_message = None
        db.commit()

        ocr_service = get_ocr_service()
        result = ocr_service.extract_text_from_pdf(document.stored_filename)
        document.ocr_text = result["full_text"]
        document.page_count = result["page_count"]
        document.ocr_pages_detail = json.dumps(result["pages"], ensure_ascii=False)
        document.status = "ocr_done"
        db.commit()
        db.refresh(document)

        text_length = len(document.ocr_text) if document.ocr_text else 0
        text_preview = document.ocr_text[:200] if document.ocr_text else ""
        return OcrProcessResponse(
            document_id=document.id,
            status=document.status,
            page_count=document.page_count or 0,
            text_length=text_length,
            text_preview=text_preview,
        )
    except Exception as exc:
        logger.exception("OCR processing failed document_id=%s", doc_id)
        document.status = "error"
        document.error_message = str(exc)
        db.commit()
        raise HTTPException(status_code=500, detail="OCR处理失败，请稍后重试") from exc
