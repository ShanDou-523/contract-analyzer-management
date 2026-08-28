"""Schemas for organization-wide risk trend and workload reports."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from schemas.risks import RiskSummary


class RiskTrendPoint(BaseModel):
    date: str
    total: int = Field(ge=0)
    open: int = Field(ge=0)
    overdue: int = Field(ge=0)
    closed: int = Field(ge=0)


class RiskContractRanking(BaseModel):
    contract_id: str
    contract_name: str
    contract_no: str | None = None
    total: int = Field(ge=0)
    open: int = Field(ge=0)
    critical: int = Field(ge=0)
    overdue: int = Field(ge=0)


class RiskAssigneeWorkload(BaseModel):
    assignee_id: str | None = None
    assignee_name: str
    total: int = Field(ge=0)
    open: int = Field(ge=0)
    overdue: int = Field(ge=0)
    closed: int = Field(ge=0)


class RiskReportOverview(BaseModel):
    generated_at: datetime
    period_days: int
    summary: RiskSummary
    trend: list[RiskTrendPoint]
    contract_rankings: list[RiskContractRanking]
    assignee_workloads: list[RiskAssigneeWorkload]


class RiskReminderScanQueued(BaseModel):
    status: Literal["queued"] = "queued"


class PagedRiskContractRankings(BaseModel):
    items: list[RiskContractRanking]
    total: int = Field(ge=0)
    page: int
    page_size: int
