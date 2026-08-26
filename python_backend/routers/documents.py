"""Document CRUD router."""

import json
import uuid
import shutil
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, Depends, Form, HTTPException, Query
from sqlalchemy.orm import Session

from config import UPLOAD_DIR, MAX_FILE_SIZE_BYTES
from database import get_db
from models.document import AnalysisResult, AnalysisTemplate, Document
from schemas.document import (
    DocumentOut,
    DocumentListItem,
    DocumentListOut,
    DocumentUploadResponse,
    AnalysisResultOut,
    DocumentTemplateUpdate,
)
from services.analysis_template_service import get_template_for_analysis

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    template_id: str | None = Form(None),
    db: Session = Depends(get_db),
):
    """Upload a PDF document."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="仅支持PDF文件格式")

    template = get_template_for_analysis(db, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="分析方案不存在，请先选择有效方案")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"文件大小超过{MAX_FILE_SIZE_BYTES // 1048576}MB限制",
        )

    doc_id = str(uuid.uuid4())
    stored_filename = f"{doc_id}.pdf"
    file_path = UPLOAD_DIR / stored_filename
    with open(file_path, "wb") as f:
        f.write(content)

    document = Document(
        id=doc_id,
        original_filename=file.filename,
        stored_filename=stored_filename,
        file_size=len(content),
        status="uploaded",
        analysis_template_id=template.id,
        analysis_template_name=template.name,
        analysis_template_version=template.version,
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return DocumentUploadResponse(
        id=document.id,
        original_filename=document.original_filename,
        status=document.status,
        message="文件上传成功",
        analysis_template_id=document.analysis_template_id,
        analysis_template_name=document.analysis_template_name,
        analysis_template_version=document.analysis_template_version,
    )


@router.get("", response_model=DocumentListOut)
def list_documents(
    template_id: str | None = Query(default=None),
    search: str | None = Query(default=None, max_length=200),
    db: Session = Depends(get_db),
):
    """List documents filtered by template, or globally searched by file name."""
    query = db.query(Document)
    search_term = search.strip() if search else ""
    if search_term:
        query = query.filter(Document.original_filename.contains(search_term, autoescape=True))
    elif template_id == "unassigned":
        query = query.filter(Document.analysis_template_id.is_(None))
    elif template_id and template_id != "all":
        query = query.filter(Document.analysis_template_id == template_id)
    documents = query.order_by(Document.created_at.desc()).all()
    items = [
        DocumentListItem(
            id=d.id,
            original_filename=d.original_filename,
            file_size=d.file_size,
            status=d.status,
            page_count=d.page_count,
            created_at=d.created_at.isoformat() if d.created_at else None,
            analysis_template_id=d.analysis_template_id,
            analysis_template_name=d.analysis_template_name,
            analysis_template_version=d.analysis_template_version,
        )
        for d in documents
    ]
    return DocumentListOut(documents=items, total=len(items))


@router.get("/{doc_id}", response_model=DocumentOut)
def get_document(doc_id: str, db: Session = Depends(get_db)):
    """Get document details including analysis results."""
    document = db.query(Document).filter(Document.id == doc_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="文档不存在")

    stored_results = db.query(AnalysisResult).filter(
        AnalysisResult.document_id == document.id
    ).order_by(AnalysisResult.created_at.desc()).all()
    latest_by_type = {}
    for result in stored_results:
        latest_by_type.setdefault(result.prompt_type, result)

    return DocumentOut(
        id=document.id,
        original_filename=document.original_filename,
        stored_filename=document.stored_filename,
        file_size=document.file_size,
        status=document.status,
        ocr_text=document.ocr_text,
        page_count=document.page_count,
        ocr_pages_detail=document.ocr_pages_detail,
        error_message=document.error_message,
        analysis_template_id=document.analysis_template_id,
        analysis_template_name=document.analysis_template_name,
        analysis_template_version=document.analysis_template_version,
        created_at=document.created_at.isoformat() if document.created_at else None,
        updated_at=document.updated_at.isoformat() if document.updated_at else None,
        analysis_results=[
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
            for r in latest_by_type.values()
        ],
    )


@router.put("/{doc_id}/template", response_model=DocumentListItem)
def assign_document_template(
    doc_id: str,
    data: DocumentTemplateUpdate,
    db: Session = Depends(get_db),
):
    """Manually classify a document without rerunning OCR or AI analysis."""
    document = db.query(Document).filter(Document.id == doc_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="文档不存在")

    template = None
    if data.template_id and data.template_id != "unassigned":
        template = db.query(AnalysisTemplate).filter(
            AnalysisTemplate.id == data.template_id
        ).first()
        if not template:
            raise HTTPException(status_code=404, detail="分析方案不存在")

    document.analysis_template_id = template.id if template else None
    document.analysis_template_name = template.name if template else None
    document.analysis_template_version = template.version if template else None
    db.commit()
    db.refresh(document)
    return DocumentListItem(
        id=document.id,
        original_filename=document.original_filename,
        file_size=document.file_size,
        status=document.status,
        page_count=document.page_count,
        created_at=document.created_at.isoformat() if document.created_at else None,
        analysis_template_id=document.analysis_template_id,
        analysis_template_name=document.analysis_template_name,
        analysis_template_version=document.analysis_template_version,
    )


@router.delete("/{doc_id}")
def delete_document(doc_id: str, db: Session = Depends(get_db)):
    """Delete a document and its files."""
    document = db.query(Document).filter(Document.id == doc_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="文档不存在")

    file_path = UPLOAD_DIR / document.stored_filename
    if file_path.exists():
        file_path.unlink()
    db.delete(document)
    db.commit()
    return {"message": "文档已删除", "id": doc_id}
