"""Organization-scoped risk ledger and remediation state transitions."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session, aliased

from models.contract import AnalysisRisk, Contract, StructuredAnalysisResult, User
from schemas.risks import ContractRiskSummary, RiskCount, RiskLedgerItem, RiskSummary

ACTIVE_REMEDIATION_STATUSES = {"open", "in_progress"}
TERMINAL_STATUSES = {"accepted", "mitigated", "dismissed", "closed"}
RISK_STATUSES = {"open", "in_progress", "accepted", "mitigated", "dismissed", "closed"}
REVIEW_ROLES = {"system_admin", "org_admin", "reviewer"}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def is_overdue(risk: AnalysisRisk, now: datetime | None = None) -> bool:
    due_at = as_utc(risk.remediation_due_at)
    if due_at is None or risk.status not in ACTIVE_REMEDIATION_STATUSES:
        return False
    return due_at < as_utc(now or now_utc())


def validate_status_transition(current: str, target: str) -> None:
    if target not in RISK_STATUSES:
        raise HTTPException(status_code=422, detail="风险状态无效")
    allowed = {
        "open": {"open", "in_progress", "accepted", "mitigated", "dismissed", "closed"},
        "in_progress": {"open", "in_progress", "accepted", "mitigated", "dismissed", "closed"},
        "accepted": {"accepted", "open", "in_progress", "closed"},
        "mitigated": {"mitigated", "open", "in_progress", "closed"},
        "dismissed": {"dismissed", "open", "in_progress", "closed"},
        "closed": {"closed", "open", "in_progress"},
    }
    if target not in allowed.get(current, set()):
        raise HTTPException(status_code=409, detail=f"风险状态不能从 {current} 变更为 {target}")


def update_risk(
    risk: AnalysisRisk,
    *,
    user_id: str,
    roles: set[str] | frozenset[str],
    status: str | None = None,
    assignee_id: str | None = None,
    remediation_due_at: datetime | None = None,
    remediation_notes: str | None = None,
    comment: str = "",
    fields_set: set[str] | frozenset[str] = frozenset(),
) -> str:
    target = status or risk.status
    if status is not None:
        validate_status_transition(risk.status, status)
        if status == "closed" and not REVIEW_ROLES.intersection(roles):
            raise HTTPException(status_code=403, detail="只有复核人员可以关闭风险")
        risk.status = status

    if "assignee_id" in fields_set:
        risk.assignee_id = assignee_id
    if "remediation_due_at" in fields_set:
        risk.remediation_due_at = remediation_due_at
    if "remediation_notes" in fields_set:
        risk.remediation_notes = remediation_notes

    clean_comment = comment.strip()
    if clean_comment:
        risk.reviewer_comment = clean_comment
        risk.reviewed_by = user_id
        risk.reviewed_at = now_utc()

    if target == "closed":
        risk.closed_by = user_id
        risk.closed_at = now_utc()
        risk.closure_comment = clean_comment or risk.closure_comment
    elif risk.status in {"open", "in_progress"} and risk.closed_at is not None:
        risk.closed_by = None
        risk.closed_at = None
        risk.closure_comment = None
    return target


def risk_base_query(db: Session, organization_id: str):
    assignee = aliased(User)
    query = (
        db.query(AnalysisRisk, Contract, StructuredAnalysisResult, assignee)
        .join(Contract, Contract.id == AnalysisRisk.contract_id)
        .join(StructuredAnalysisResult, StructuredAnalysisResult.id == AnalysisRisk.structured_result_id)
        .outerjoin(assignee, assignee.id == AnalysisRisk.assignee_id)
        .filter(
            AnalysisRisk.organization_id == organization_id,
            Contract.organization_id == organization_id,
            Contract.deleted_at.is_(None),
            StructuredAnalysisResult.organization_id == organization_id,
            StructuredAnalysisResult.status != "superseded",
        )
    )
    return query


def to_ledger_item(row, now: datetime | None = None) -> RiskLedgerItem:
    risk, contract, result, assignee = row
    return RiskLedgerItem(
        id=risk.id,
        organization_id=risk.organization_id,
        contract_id=risk.contract_id,
        contract_name=contract.name,
        contract_no=contract.contract_no,
        structured_result_id=risk.structured_result_id,
        prompt_type=result.prompt_type,
        result_version=result.version,
        evidence_id=risk.evidence_id,
        code=risk.code,
        title=risk.title,
        description=risk.description,
        severity=risk.severity,
        status=risk.status,
        assignee_id=risk.assignee_id,
        assignee_name=assignee.display_name if assignee else None,
        remediation_due_at=risk.remediation_due_at,
        remediation_notes=risk.remediation_notes,
        reviewer_comment=risk.reviewer_comment,
        reviewed_by=risk.reviewed_by,
        reviewed_at=risk.reviewed_at,
        closed_by=risk.closed_by,
        closed_at=risk.closed_at,
        closure_comment=risk.closure_comment,
        is_overdue=is_overdue(risk, now),
        created_at=risk.created_at,
        updated_at=risk.updated_at,
    )


def _counts(rows: list[AnalysisRisk], now: datetime | None = None) -> RiskSummary:
    status_counts = {status: 0 for status in RISK_STATUSES}
    severity_counts = {severity: 0 for severity in ("low", "medium", "high", "critical")}
    overdue = 0
    for risk in rows:
        status_counts[risk.status] = status_counts.get(risk.status, 0) + 1
        severity_counts[risk.severity] = severity_counts.get(risk.severity, 0) + 1
        overdue += int(is_overdue(risk, now))
    return RiskSummary(
        total=len(rows),
        open=status_counts["open"],
        in_progress=status_counts["in_progress"],
        accepted=status_counts["accepted"],
        mitigated=status_counts["mitigated"],
        dismissed=status_counts["dismissed"],
        closed=status_counts["closed"],
        overdue=overdue,
        by_severity=[RiskCount(key=key, count=severity_counts[key]) for key in severity_counts],
        by_status=[RiskCount(key=key, count=status_counts[key]) for key in status_counts],
    )


def summarize_risks(db: Session, organization_id: str, contract_id: str | None = None) -> RiskSummary:
    query = (
        db.query(AnalysisRisk)
        .join(Contract, Contract.id == AnalysisRisk.contract_id)
        .join(StructuredAnalysisResult, StructuredAnalysisResult.id == AnalysisRisk.structured_result_id)
        .filter(
            AnalysisRisk.organization_id == organization_id,
            Contract.organization_id == organization_id,
            Contract.deleted_at.is_(None),
            StructuredAnalysisResult.organization_id == organization_id,
            StructuredAnalysisResult.status != "superseded",
        )
    )
    if contract_id:
        query = query.filter(AnalysisRisk.contract_id == contract_id)
    return _counts(query.all())


def contract_summary(db: Session, organization_id: str, contract: Contract) -> ContractRiskSummary:
    summary = summarize_risks(db, organization_id, contract.id)
    return ContractRiskSummary(
        contract_id=contract.id,
        contract_name=contract.name,
        contract_no=contract.contract_no,
        **summary.model_dump(),
    )
