"""Organization-scoped contract master-data endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from core.security import CurrentPrincipal, get_current_principal, require_roles
from database import get_db
from models.contract import Contract
from schemas.contracts import ContractCreate, ContractOut, PagedContracts
from services.audit_service import record_audit

router = APIRouter(prefix="/api/v1/contracts", tags=["contracts"])


@router.get("", response_model=PagedContracts)
def list_contracts(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None, max_length=200),
    status: str | None = Query(default=None, max_length=32),
    principal: CurrentPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    query = db.query(Contract).filter(
        Contract.organization_id == principal.organization_id,
        Contract.deleted_at.is_(None),
    )
    if search and search.strip():
        term = search.strip()
        query = query.filter(
            Contract.name.contains(term, autoescape=True)
            | Contract.contract_no.contains(term, autoescape=True)
        )
    if status:
        query = query.filter(Contract.status == status)
    total = query.count()
    items = (
        query.order_by(Contract.updated_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return PagedContracts(items=items, total=total, page=page, page_size=page_size)


@router.post("", response_model=ContractOut, status_code=201)
def create_contract(
    data: ContractCreate,
    principal: CurrentPrincipal = Depends(
        require_roles("system_admin", "org_admin", "contract_manager")
    ),
    db: Session = Depends(get_db),
):
    if data.contract_no:
        duplicate = (
            db.query(Contract)
            .filter(
                Contract.organization_id == principal.organization_id,
                Contract.contract_no == data.contract_no,
                Contract.deleted_at.is_(None),
            )
            .first()
        )
        if duplicate:
            raise HTTPException(status_code=409, detail="合同编号已存在")
    contract = Contract(
        organization_id=principal.organization_id,
        created_by=principal.user_id,
        updated_by=principal.user_id,
        source="manual",
        **data.model_dump(),
    )
    db.add(contract)
    db.flush()
    record_audit(
        db,
        "contract.created",
        organization_id=principal.organization_id,
        user_id=principal.user_id,
        resource_type="contract",
        resource_id=contract.id,
        details={"contract_no": contract.contract_no},
    )
    db.commit()
    db.refresh(contract)
    return contract


@router.get("/{contract_id}", response_model=ContractOut)
def get_contract(
    contract_id: str,
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
    return contract
