"""Schemas for organization-wide risk remediation and collaboration."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

RiskSeverity = Literal["low", "medium", "high", "critical"]
RiskStatus = Literal["open", "in_progress", "accepted", "mitigated", "dismissed", "closed"]


class RiskRemediationUpdate(BaseModel):
    status: RiskStatus | None = None
    assignee_id: str | None = None
    remediation_due_at: datetime | None = None
    remediation_notes: str | None = Field(default=None, max_length=20_000)
    comment: str = Field(default="", max_length=5_000)

    @model_validator(mode="after")
    def require_status_comment(self):
        if self.status in {"accepted", "mitigated", "dismissed", "closed"} and not self.comment.strip():
            raise ValueError("完成或关闭风险整改必须填写复核意见")
        return self


class RiskLedgerItem(BaseModel):
    id: str
    organization_id: str
    contract_id: str
    contract_name: str
    contract_no: str | None = None
    structured_result_id: str
    prompt_type: str
    result_version: int
    evidence_id: str | None = None
    code: str | None = None
    title: str
    description: str
    severity: RiskSeverity
    status: RiskStatus
    assignee_id: str | None = None
    assignee_name: str | None = None
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
    updated_at: datetime


class PagedRisks(BaseModel):
    items: list[RiskLedgerItem]
    total: int
    page: int
    page_size: int


class RiskCount(BaseModel):
    key: str
    count: int


class RiskSummary(BaseModel):
    total: int
    open: int
    in_progress: int
    accepted: int
    mitigated: int
    dismissed: int
    closed: int
    overdue: int
    by_severity: list[RiskCount]
    by_status: list[RiskCount]


class ContractRiskSummary(RiskSummary):
    contract_id: str
    contract_name: str
    contract_no: str | None = None


class ContractRisksOut(BaseModel):
    summary: ContractRiskSummary
    items: list[RiskLedgerItem]
