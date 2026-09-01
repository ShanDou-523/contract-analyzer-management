"""Schemas for asynchronous batch PDF imports."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

BatchStatus = Literal["queued", "running", "completed", "partial", "failed", "cancelled"]
BatchItemStatus = Literal[
    "queued", "ocr_processing", "ocr_done", "analyzing", "done", "error"
]


class BatchImportItemOut(BaseModel):
    id: str
    batch_id: str
    organization_id: str
    document_id: str | None = None
    original_filename: str
    file_size: int
    status: BatchItemStatus
    stage: Literal["ocr", "analysis"]
    progress: int = Field(ge=0, le=100)
    ocr_job_id: str | None = None
    analysis_job_id: str | None = None
    retry_count: int
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class BatchImportOut(BaseModel):
    id: str
    organization_id: str
    created_by: str
    template_id: str | None = None
    status: BatchStatus
    total_count: int
    completed_count: int
    failed_count: int
    progress: int = Field(ge=0, le=100)
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    updated_at: datetime
    items: list[BatchImportItemOut]


class PagedBatchImports(BaseModel):
    items: list[BatchImportOut]
    total: int
    page: int
    page_size: int


class BatchImportQueued(BaseModel):
    id: str
    status: BatchStatus
    total_count: int
    message: str = "批量导入已排队"
