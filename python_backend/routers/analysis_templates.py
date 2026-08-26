"""CRUD endpoints for reusable contract analysis templates."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models.document import AnalysisTemplate, Document
from schemas.analysis_template import AnalysisTemplateOut, AnalysisTemplateWrite
from services.analysis_template_service import decode_fields, encode_fields

router = APIRouter(prefix="/api/analysis-templates", tags=["analysis-templates"])


def _to_out(template: AnalysisTemplate, db: Session) -> AnalysisTemplateOut:
    return AnalysisTemplateOut(
        id=template.id,
        name=template.name,
        description=template.description,
        analysis_focus=template.analysis_focus,
        fields=decode_fields(template),
        review_enabled=template.review_enabled,
        review_instructions=template.review_instructions,
        version=template.version,
        is_default=template.is_default,
        document_count=db.query(Document).filter(
            Document.analysis_template_id == template.id
        ).count(),
        created_at=template.created_at.isoformat() if template.created_at else None,
        updated_at=template.updated_at.isoformat() if template.updated_at else None,
    )


def _get_template(template_id: str, db: Session) -> AnalysisTemplate:
    template = db.query(AnalysisTemplate).filter(AnalysisTemplate.id == template_id).first()
    if not template:
        raise HTTPException(status_code=404, detail="分析方案不存在")
    return template


def _ensure_unique_name(name: str, db: Session, exclude_id: str | None = None) -> None:
    query = db.query(AnalysisTemplate).filter(AnalysisTemplate.name == name)
    if exclude_id:
        query = query.filter(AnalysisTemplate.id != exclude_id)
    if query.first():
        raise HTTPException(status_code=409, detail="分析方案名称已存在")


@router.get("", response_model=list[AnalysisTemplateOut])
def list_templates(db: Session = Depends(get_db)):
    templates = db.query(AnalysisTemplate).order_by(
        AnalysisTemplate.is_default.desc(), AnalysisTemplate.updated_at.desc()
    ).all()
    return [_to_out(template, db) for template in templates]


@router.post("", response_model=AnalysisTemplateOut)
def create_template(data: AnalysisTemplateWrite, db: Session = Depends(get_db)):
    _ensure_unique_name(data.name, db)
    template = AnalysisTemplate(
        id=str(uuid.uuid4()),
        name=data.name,
        description=data.description,
        analysis_focus=data.analysis_focus,
        fields_json=encode_fields([field.model_dump() for field in data.fields]),
        review_enabled=data.review_enabled,
        review_instructions=data.review_instructions,
        version=1,
        is_default=db.query(AnalysisTemplate).count() == 0,
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return _to_out(template, db)


@router.put("/{template_id}", response_model=AnalysisTemplateOut)
def update_template(template_id: str, data: AnalysisTemplateWrite, db: Session = Depends(get_db)):
    template = _get_template(template_id, db)
    _ensure_unique_name(data.name, db, exclude_id=template_id)
    template.name = data.name
    template.description = data.description
    template.analysis_focus = data.analysis_focus
    template.fields_json = encode_fields([field.model_dump() for field in data.fields])
    template.review_enabled = data.review_enabled
    template.review_instructions = data.review_instructions
    template.version += 1
    db.query(Document).filter(
        Document.analysis_template_id == template.id
    ).update(
        {
            Document.analysis_template_name: template.name,
        },
        synchronize_session=False,
    )
    db.commit()
    db.refresh(template)
    return _to_out(template, db)


@router.delete("/{template_id}")
def delete_template(template_id: str, db: Session = Depends(get_db)):
    template = _get_template(template_id, db)
    if db.query(AnalysisTemplate).count() <= 1:
        raise HTTPException(status_code=400, detail="至少需要保留一个分析方案")
    if template.is_default:
        raise HTTPException(status_code=400, detail="请先将其他方案设为默认方案")
    db.query(Document).filter(
        Document.analysis_template_id == template.id
    ).update(
        {
            Document.analysis_template_id: None,
            Document.analysis_template_name: f"{template.name}（已删除）",
            Document.analysis_template_version: template.version,
        },
        synchronize_session=False,
    )
    db.delete(template)
    db.commit()
    return {"message": "分析方案已删除", "id": template_id}


@router.post("/{template_id}/duplicate", response_model=AnalysisTemplateOut)
def duplicate_template(template_id: str, db: Session = Depends(get_db)):
    source = _get_template(template_id, db)
    base_name = f"{source.name} 副本"
    name = base_name
    suffix = 2
    while db.query(AnalysisTemplate).filter(AnalysisTemplate.name == name).first():
        name = f"{base_name} {suffix}"
        suffix += 1
    fields = decode_fields(source)
    for field in fields:
        field["id"] = str(uuid.uuid4())
    template = AnalysisTemplate(
        id=str(uuid.uuid4()),
        name=name,
        description=source.description,
        analysis_focus=source.analysis_focus,
        fields_json=encode_fields(fields),
        review_enabled=source.review_enabled,
        review_instructions=source.review_instructions,
        version=1,
        is_default=False,
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return _to_out(template, db)


@router.post("/{template_id}/set-default", response_model=AnalysisTemplateOut)
def set_default_template(template_id: str, db: Session = Depends(get_db)):
    template = _get_template(template_id, db)
    db.query(AnalysisTemplate).update({AnalysisTemplate.is_default: False})
    template.is_default = True
    db.commit()
    db.refresh(template)
    return _to_out(template, db)
