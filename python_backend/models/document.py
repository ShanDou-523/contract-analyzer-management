"""Document ORM model."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from database import Base


class Document(Base):
    __tablename__ = "documents"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    original_filename = Column(String(512), nullable=False)
    stored_filename = Column(String(512), nullable=False)
    file_size = Column(Integer, nullable=False, default=0)
    status = Column(String(20), nullable=False, default="uploaded", index=True)
    ocr_text = Column(Text, nullable=True)
    page_count = Column(Integer, nullable=True)
    ocr_pages_detail = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    analysis_template_id = Column(String(36), nullable=True, index=True)
    analysis_template_name = Column(String(100), nullable=True)
    analysis_template_version = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    analysis_results = relationship(
        "AnalysisResult",
        backref="document",
        cascade="all, delete-orphan",
        order_by="AnalysisResult.created_at.desc()",
    )

    def to_dict(self, include_results=False):
        d = {
            "id": self.id,
            "original_filename": self.original_filename,
            "stored_filename": self.stored_filename,
            "file_size": self.file_size,
            "status": self.status,
            "ocr_text": self.ocr_text,
            "page_count": self.page_count,
            "ocr_pages_detail": self.ocr_pages_detail,
            "error_message": self.error_message,
            "analysis_template_id": self.analysis_template_id,
            "analysis_template_name": self.analysis_template_name,
            "analysis_template_version": self.analysis_template_version,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        if include_results:
            d["analysis_results"] = [r.to_dict() for r in self.analysis_results]
        return d


class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(String(36), ForeignKey("documents.id"), nullable=False, index=True)
    prompt_type = Column(String(50), nullable=False)
    prompt_text = Column(Text, nullable=False)
    response_text = Column(Text, nullable=True)
    tokens_used = Column(Integer, nullable=True)
    # Kept as a nullable compatibility link; the domain model owns the run FK.
    analysis_run_id = Column(String(36), nullable=True, index=True)
    template_id = Column(String(36), nullable=True)
    template_name = Column(String(100), nullable=True)
    template_version = Column(Integer, nullable=True)
    fields_snapshot_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            "id": self.id,
            "document_id": self.document_id,
            "prompt_type": self.prompt_type,
            "prompt_text": self.prompt_text,
            "response_text": self.response_text,
            "tokens_used": self.tokens_used,
            "template_id": self.template_id,
            "template_name": self.template_name,
            "template_version": self.template_version,
            "fields_snapshot_json": self.fields_snapshot_json,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AnalysisTemplate(Base):
    """Reusable extraction and review configuration for one contract category."""

    __tablename__ = "analysis_templates"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=False, default="")
    analysis_focus = Column(Text, nullable=False, default="")
    fields_json = Column(Text, nullable=False, default="[]")
    review_enabled = Column(Boolean, nullable=False, default=True)
    review_instructions = Column(Text, nullable=False, default="")
    version = Column(Integer, nullable=False, default=1)
    is_default = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class Setting(Base):
    """Key-value settings store (API keys, etc.)."""

    __tablename__ = "settings"

    key = Column(String(128), primary_key=True)
    value = Column(Text, nullable=False, default="")

    @staticmethod
    def get(db, key: str, default: str = "") -> str:
        row = db.query(Setting).filter(Setting.key == key).first()
        return row.value if row else default

    @staticmethod
    def set(db, key: str, value: str):
        row = db.query(Setting).filter(Setting.key == key).first()
        if row:
            row.value = value
        else:
            db.add(Setting(key=key, value=value))
        db.commit()

    @staticmethod
    def get_all(db) -> dict:
        rows = db.query(Setting).all()
        return {r.key: r.value for r in rows}
