"""Schemas for versioned structured analysis, evidence, risk, and review."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

StructuredStatus = Literal["draft", "in_review", "approved", "rejected", "superseded"]
RiskSeverity = Literal["low", "medium", "high", "critical"]
RiskStatus = Literal["open", "in_progress", "accepted", "mitigated", "dismissed", "closed"]


class StructuredFieldInput(BaseModel):
    field_key: str = Field(min_length=1, max_length=128)
    label: str = Field(min_length=1, max_length=200)
    value: Any = None
    confidence: float | None = Field(default=None, ge=0, le=1)


class EvidenceInput(BaseModel):
    page_no: int | None = Field(default=None, ge=1)
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)
    quote: str = Field(default="", max_length=20_000)
    locator: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_offsets(self):
        if self.char_end is not None and self.char_start is None:
            raise ValueError("填写结束位置时必须同时填写开始位置")
        if (
            self.char_start is not None
            and self.char_end is not None
            and self.char_end < self.char_start
        ):
            raise ValueError("证据结束位置不能早于开始位置")
        return self


class RiskInput(BaseModel):
    code: str | None = Field(default=None, max_length=100)
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=20_000)
    severity: RiskSeverity = "medium"
    status: RiskStatus = "open"
    reviewer_comment: str | None = Field(default=None, max_length=5000)
    evidence_index: int | None = Field(default=None, ge=0)


class StructuredResultCreate(BaseModel):
    prompt_type: str = Field(min_length=1, max_length=50)
    source_result_id: str | None = None
    summary: str = Field(default="", max_length=20_000)
    fields: list[StructuredFieldInput] = Field(default_factory=list, max_length=500)
    evidence: list[EvidenceInput] = Field(default_factory=list, max_length=500)
    risks: list[RiskInput] = Field(default_factory=list, max_length=500)


class StructuredRevisionCreate(BaseModel):
    summary: str = Field(default="", max_length=20_000)
    fields: list[StructuredFieldInput] = Field(default_factory=list, max_length=500)
    evidence: list[EvidenceInput] = Field(default_factory=list, max_length=500)
    risks: list[RiskInput] = Field(default_factory=list, max_length=500)


class ReviewDecision(BaseModel):
    decision: Literal["approved", "rejected"]
    comment: str = Field(default="", max_length=5000)

    @model_validator(mode="after")
    def require_rejection_comment(self):
        if self.decision == "rejected" and not self.comment.strip():
            raise ValueError("驳回复核必须填写意见")
        return self


class RiskStatusUpdate(BaseModel):
    status: RiskStatus
    comment: str = Field(default="", max_length=5000)

    @model_validator(mode="after")
    def require_resolution_comment(self):
        if self.status in {"accepted", "mitigated", "dismissed", "closed"} and not self.comment.strip():
            raise ValueError("处置风险项必须填写复核意见")
        return self


class StructuredFieldOut(BaseModel):
    id: str
    field_key: str
    label: str
    value: Any = None
    value_text: str
    confidence: float | None = None
    position: int


class EvidenceOut(BaseModel):
    id: str
    file_version_id: str
    page_no: int | None = None
    char_start: int | None = None
    char_end: int | None = None
    quote: str
    locator: dict[str, Any]
    created_at: datetime


class RiskOut(BaseModel):
    id: str
    evidence_id: str | None = None
    code: str | None = None
    title: str
    description: str
    severity: RiskSeverity
    status: RiskStatus
    assignee_id: str | None = None
    remediation_due_at: datetime | None = None
    remediation_notes: str | None = None
    reviewer_comment: str | None = None
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    closed_by: str | None = None
    closed_at: datetime | None = None
    closure_comment: str | None = None
    is_overdue: bool = False
    created_at: datetime


class StructuredResultOut(BaseModel):
    id: str
    organization_id: str
    contract_id: str
    analysis_run_id: str
    source_result_id: str | None = None
    file_version_id: str
    template_version_id: str
    prompt_type: str
    version: int
    status: StructuredStatus
    summary: str
    created_by: str
    reviewed_by: str | None = None
    review_comment: str | None = None
    reviewed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    fields: list[StructuredFieldOut]
    evidence: list[EvidenceOut]
    risks: list[RiskOut]


class AnalysisRunOut(BaseModel):
    id: str
    contract_id: str
    contract_name: str
    contract_no: str | None = None
    file_version_id: str | None = None
    file_name: str | None = None
    template_version_id: str | None = None
    template_name: str | None = None
    template_version: int | None = None
    task_type: str
    status: str
    provider_name: str | None = None
    model_name: str | None = None
    requested_by: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime
    raw_result_count: int
    structured_results: list[StructuredResultOut]
