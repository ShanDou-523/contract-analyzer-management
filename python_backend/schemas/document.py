"""Pydantic schemas for Document."""

from typing import Any, Optional, List

from pydantic import BaseModel


class DocumentOut(BaseModel):
    id: str
    original_filename: str
    stored_filename: str
    file_size: int
    status: str
    ocr_text: Optional[str] = None
    page_count: Optional[int] = None
    ocr_pages_detail: Optional[str] = None
    error_message: Optional[str] = None
    analysis_template_id: Optional[str] = None
    analysis_template_name: Optional[str] = None
    analysis_template_version: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    analysis_results: List["AnalysisResultOut"] = []

    class Config:
        from_attributes = True


class AnalysisResultOut(BaseModel):
    id: str
    document_id: str
    prompt_type: str
    prompt_text: str
    response_text: Optional[str] = None
    tokens_used: Optional[int] = None
    template_id: Optional[str] = None
    template_name: Optional[str] = None
    template_version: Optional[int] = None
    fields_snapshot: Optional[list[dict[str, Any]]] = None
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


DocumentOut.model_rebuild()


class DocumentListItem(BaseModel):
    id: str
    original_filename: str
    file_size: int
    status: str
    page_count: Optional[int] = None
    created_at: Optional[str] = None
    analysis_template_id: Optional[str] = None
    analysis_template_name: Optional[str] = None
    analysis_template_version: Optional[int] = None

    class Config:
        from_attributes = True


class DocumentListOut(BaseModel):
    documents: List[DocumentListItem]
    total: int


class DocumentUploadResponse(BaseModel):
    id: str
    original_filename: str
    status: str
    message: str
    analysis_template_id: Optional[str] = None
    analysis_template_name: Optional[str] = None
    analysis_template_version: Optional[int] = None


class DocumentTemplateUpdate(BaseModel):
    template_id: Optional[str] = None
