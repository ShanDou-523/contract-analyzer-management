"""Pydantic schemas for Analysis."""

from typing import Any, Optional

from pydantic import BaseModel


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


class OcrProcessResponse(BaseModel):
    document_id: str
    status: str
    page_count: int
    text_length: int
    text_preview: str


class AnalysisResponse(BaseModel):
    document_id: str
    status: str
    results: list[AnalysisResultOut]


class AnalyzeRequest(BaseModel):
    template_id: Optional[str] = None
