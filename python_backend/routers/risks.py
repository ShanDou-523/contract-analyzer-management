"""Organization-wide contract risk ledger and remediation collaboration APIs."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import asc, desc, or_
from sqlalchemy.orm import Session

from core.security import CurrentPrincipal, get_current_principal, require_roles
from database import get_db
from models.contract import AnalysisRisk, Contract, StructuredAnalysisResult, User
from schemas.risks import (
    ContractRisksOut,
    PagedRisks,
    RiskLedgerItem,
    RiskRemediationUpdate,
    RiskSummary,
)
from services.audit_service import record_audit
from services.risk_service import (
    ACTIVE_REMEDIATION_STATUSES,
    contract_summary,
    risk_base_query,
    summarize_risks,
    to_ledger_item,
    update_risk,
)

router = APIRouter(prefix="/api/v1", tags=["risks"])
RISK_MANAGE_ROLES = ("system_admin", "org_admin", "contract_manager", "reviewer")
SORT_COLUMNS = {
    "created_at": AnalysisRisk.created_at,
    "updated_at": AnalysisRisk.updated_at,
    "remediation_due_at": AnalysisRisk.remediation_due_at,
    "severity": AnalysisRisk.severity,
    "status": AnalysisRisk.status,
}


def _get_risk_row(db: Session, principal: CurrentPrincipal, risk_id: str):
    row = (
        risk_base_query(db, principal.organization_id)
        .filter(AnalysisRisk.id == risk_id)
        .one_or_none()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="风险项不存在")
    return row


@router.get("/risks/summary", response_model=RiskSummary)
def get_risk_summary(
    principal: CurrentPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    return summarize_risks(db, principal.organization_id)


@router.get("/risks", response_model=PagedRisks)
def list_risks(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None, max_length=200),
    status: str | None = Query(default=None, pattern=r"^(open|in_progress|accepted|mitigated|dismissed|closed)$"),
    severity: str | None = Query(default=None, pattern=r"^(low|medium|high|critical)$"),
    contract_id: str | None = Query(default=None),
    assignee_id: str | None = Query(default=None),
    overdue_only: bool = Query(default=False),
    sort_by: str = Query(default="remediation_due_at", pattern=r"^(created_at|updated_at|remediation_due_at|severity|status)$"),
    sort_order: str = Query(default="asc", pattern=r"^(asc|desc)$"),
    principal: CurrentPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    query = risk_base_query(db, principal.organization_id)
    if search and search.strip():
        term = search.strip()
        query = query.filter(
            or_(
                AnalysisRisk.title.contains(term, autoescape=True),
                AnalysisRisk.description.contains(term, autoescape=True),
                Contract.name.contains(term, autoescape=True),
                Contract.contract_no.contains(term, autoescape=True),
            )
        )
    if status:
        query = query.filter(AnalysisRisk.status == status)
    if severity:
        query = query.filter(AnalysisRisk.severity == severity)
    if contract_id:
        query = query.filter(AnalysisRisk.contract_id == contract_id)
    if assignee_id:
        query = query.filter(AnalysisRisk.assignee_id == assignee_id)
    if overdue_only:
        query = query.filter(
            AnalysisRisk.status.in_(ACTIVE_REMEDIATION_STATUSES),
            AnalysisRisk.remediation_due_at.isnot(None),
            AnalysisRisk.remediation_due_at < datetime.now(timezone.utc),
        )
    total = query.count()
    column = SORT_COLUMNS[sort_by]
    ordering = asc(column).nulls_last() if sort_order == "asc" else desc(column).nulls_last()
    rows = query.order_by(ordering, AnalysisRisk.id.asc()).offset((page - 1) * page_size).limit(page_size).all()
    return PagedRisks(
        items=[to_ledger_item(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/contracts/{contract_id}/risks", response_model=ContractRisksOut)
def list_contract_risks(
    contract_id: str,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=100),
    principal: CurrentPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    contract = (
        db.query(Contract)
        .filter(
            Contract.id == contract_id,
            Contract.organization_id == principal.organization_id,
            Contract.deleted_at.is_(None),
        )
        .one_or_none()
    )
    if contract is None:
        raise HTTPException(status_code=404, detail="合同不存在")
    rows = (
        risk_base_query(db, principal.organization_id)
        .filter(AnalysisRisk.contract_id == contract.id)
        .order_by(AnalysisRisk.created_at.desc(), AnalysisRisk.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return ContractRisksOut(summary=contract_summary(db, principal.organization_id, contract), items=[to_ledger_item(row) for row in rows])


@router.patch("/risks/{risk_id}", response_model=RiskLedgerItem)
def update_risk_remediation(
    risk_id: str,
    data: RiskRemediationUpdate,
    principal: CurrentPrincipal = Depends(require_roles(*RISK_MANAGE_ROLES)),
    db: Session = Depends(get_db),
):
    row = _get_risk_row(db, principal, risk_id)
    risk, contract, result, _assignee = row
    before = {
        "status": risk.status,
        "assignee_id": risk.assignee_id,
        "remediation_due_at": risk.remediation_due_at.isoformat() if risk.remediation_due_at else None,
        "remediation_notes": risk.remediation_notes,
    }
    if "assignee_id" in data.model_fields_set and data.assignee_id:
        assignee = (
            db.query(User)
            .filter(User.id == data.assignee_id, User.organization_id == principal.organization_id, User.status == "active")
            .one_or_none()
        )
        if assignee is None:
            raise HTTPException(status_code=422, detail="整改负责人不存在或已停用")
    update_risk(
        risk,
        user_id=principal.user_id,
        roles=principal.roles,
        status=data.status,
        assignee_id=data.assignee_id,
        remediation_due_at=data.remediation_due_at,
        remediation_notes=data.remediation_notes,
        comment=data.comment,
        fields_set=data.model_fields_set,
    )
    after = {
        "status": risk.status,
        "assignee_id": risk.assignee_id,
        "remediation_due_at": risk.remediation_due_at.isoformat() if risk.remediation_due_at else None,
        "remediation_notes": risk.remediation_notes,
    }
    record_audit(
        db,
        "risk.remediation_updated",
        organization_id=principal.organization_id,
        user_id=principal.user_id,
        resource_type="analysis_risk",
        resource_id=risk.id,
        details={"contract_id": contract.id, "structured_result_id": result.id, "before": before, "after": after},
    )
    db.commit()
    db.expire_all()
    return to_ledger_item(_get_risk_row(db, principal, risk.id))
