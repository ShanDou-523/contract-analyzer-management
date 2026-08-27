"""Contract details, parties, contacts, fulfillment tasks, and operation history."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from core.security import CurrentPrincipal, as_utc, get_current_principal, require_roles
from database import get_db
from models.contract import (
    AuditLog,
    Contact,
    Contract,
    ContractFile,
    ContractParty,
    FulfillmentTask,
    Party,
    User,
)
from schemas.contracts import ContractFileOut
from schemas.fulfillment import (
    ContactCreate,
    ContactOut,
    ContactUpdate,
    ContractDetailOut,
    ContractOperationOut,
    ContractPartyLinkCreate,
    ContractPartyOut,
    FulfillmentAssigneeOut,
    FulfillmentTaskCreate,
    FulfillmentTaskOut,
    FulfillmentTaskUpdate,
    PartyCreate,
    PartyOut,
    PartyUpdate,
)
from services.audit_service import record_audit
from services.fulfillment_service import (
    ensure_assignee,
    task_is_overdue,
    validate_schedule,
    validate_transition,
)

router = APIRouter(prefix="/api/v1", tags=["fulfillment"])
MANAGE_ROLES = ("system_admin", "org_admin", "contract_manager")


def _get_contract(
    db: Session, principal: CurrentPrincipal, contract_id: str, *, include_deleted: bool = False
) -> Contract:
    query = db.query(Contract).filter(
        Contract.id == contract_id, Contract.organization_id == principal.organization_id
    )
    if not include_deleted:
        query = query.filter(Contract.deleted_at.is_(None))
    contract = query.one_or_none()
    if contract is None:
        raise HTTPException(status_code=404, detail="合同不存在")
    return contract


def _party_out(party: Party) -> PartyOut:
    return PartyOut.model_validate(party)


def _contact_out(contact: Contact) -> ContactOut:
    return ContactOut.model_validate(contact)


def _party_link_out(link: ContractParty) -> ContractPartyOut:
    return ContractPartyOut(
        id=link.id,
        contract_id=link.contract_id,
        role=link.role,
        notes=link.notes,
        party=_party_out(link.party),
        contacts=[_contact_out(contact) for contact in link.party.contacts if contact.status == "active"],
    )


def _task_out(task: FulfillmentTask) -> FulfillmentTaskOut:
    return FulfillmentTaskOut(
        id=task.id,
        organization_id=task.organization_id,
        contract_id=task.contract_id,
        title=task.title,
        description=task.description,
        task_type=task.task_type,
        status=task.status,
        priority=task.priority,
        assignee_id=task.assignee_id,
        due_at=task.due_at,
        remind_at=task.remind_at,
        completed_at=task.completed_at,
        completed_by=task.completed_by,
        created_by=task.created_by,
        updated_by=task.updated_by,
        created_at=task.created_at,
        updated_at=task.updated_at,
        is_overdue=task_is_overdue(task),
    )


def _operation_out(entry: AuditLog) -> ContractOperationOut:
    try:
        details = json.loads(entry.details_json or "{}")
        if not isinstance(details, dict):
            details = {}
    except json.JSONDecodeError:
        details = {}
    return ContractOperationOut(
        id=entry.id,
        action=entry.action,
        resource_type=entry.resource_type,
        resource_id=entry.resource_id,
        details=details,
        user_id=entry.user_id,
        created_at=entry.created_at,
    )


def _files_for_contract(db: Session, contract: Contract) -> list[ContractFileOut]:
    files = (
        db.query(ContractFile)
        .filter(ContractFile.contract_id == contract.id, ContractFile.deleted_at.is_(None))
        .order_by(ContractFile.purpose, ContractFile.created_at)
        .all()
    )
    return [
        ContractFileOut(
            id=contract_file.id,
            contract_id=contract_file.contract_id,
            purpose=contract_file.purpose,
            current_version_id=contract_file.current_version_id,
            versions=[
                _version_out(contract.id, version)
                for version in sorted(
                    (item for item in contract_file.versions if item.deleted_at is None),
                    key=lambda item: item.version_no,
                    reverse=True,
                )
            ],
        )
        for contract_file in files
    ]


def _version_out(contract_id: str, version) -> object:
    from routers.contracts import _version_out as base_version_out

    return base_version_out(contract_id, version)


def _operations_for_contract(db: Session, principal: CurrentPrincipal, contract_id: str):
    pattern = f'"contract_id": "{contract_id}"'
    party_ids = [
        party_id
        for (party_id,) in db.query(ContractParty.party_id)
        .filter(ContractParty.contract_id == contract_id)
        .all()
    ]
    resource_ids = [contract_id, *party_ids]
    entries = (
        db.query(AuditLog)
        .filter(
            AuditLog.organization_id == principal.organization_id,
            or_(
                AuditLog.resource_id.in_(resource_ids),
                AuditLog.details_json.contains(pattern),
            ),
        )
        .order_by(AuditLog.created_at.desc())
        .limit(200)
        .all()
    )
    return [_operation_out(entry) for entry in entries]


@router.get("/contracts/{contract_id}/detail", response_model=ContractDetailOut)
def contract_detail(
    contract_id: str,
    principal: CurrentPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    contract = _get_contract(db, principal, contract_id)
    links = (
        db.query(ContractParty)
        .join(Party, ContractParty.party_id == Party.id)
        .filter(
            ContractParty.contract_id == contract.id,
            Party.organization_id == principal.organization_id,
        )
        .order_by(ContractParty.role, ContractParty.created_at)
        .all()
    )
    tasks = (
        db.query(FulfillmentTask)
        .filter(
            FulfillmentTask.contract_id == contract.id,
            FulfillmentTask.organization_id == principal.organization_id,
        )
        .order_by(FulfillmentTask.due_at.asc(), FulfillmentTask.created_at.asc())
        .all()
    )
    return ContractDetailOut(
        contract=contract,
        files=_files_for_contract(db, contract),
        parties=[_party_link_out(link) for link in links],
        tasks=[_task_out(task) for task in tasks],
        operations=_operations_for_contract(db, principal, contract.id),
    )


@router.get("/contracts/{contract_id}/operations", response_model=list[ContractOperationOut])
def contract_operations(
    contract_id: str,
    principal: CurrentPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    _get_contract(db, principal, contract_id)
    return _operations_for_contract(db, principal, contract_id)


@router.get("/parties", response_model=list[PartyOut])
def list_parties(
    party_type: str | None = Query(default=None, pattern=r"^(party_a|party_b|other)$"),
    search: str | None = Query(default=None, max_length=200),
    principal: CurrentPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    query = db.query(Party).filter(
        Party.organization_id == principal.organization_id, Party.status == "active"
    )
    if party_type:
        query = query.filter(Party.party_type == party_type)
    if search and search.strip():
        query = query.filter(Party.name.contains(search.strip(), autoescape=True))
    return query.order_by(Party.name.asc()).all()


@router.get("/fulfillment-assignees", response_model=list[FulfillmentAssigneeOut])
def list_fulfillment_assignees(
    principal: CurrentPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    """Return the active users that may be assigned within the current organization."""
    return (
        db.query(User.id, User.display_name)
        .filter(
            User.organization_id == principal.organization_id,
            User.status == "active",
        )
        .order_by(User.display_name.asc(), User.username.asc())
        .all()
    )


@router.post("/parties", response_model=PartyOut, status_code=201)
def create_party(
    data: PartyCreate,
    principal: CurrentPrincipal = Depends(require_roles(*MANAGE_ROLES)),
    db: Session = Depends(get_db),
):
    duplicate = db.query(Party).filter(
        Party.organization_id == principal.organization_id,
        Party.party_type == data.party_type,
        Party.name == data.name,
    ).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="同类型主体已存在")
    party = Party(organization_id=principal.organization_id, **data.model_dump())
    db.add(party)
    db.flush()
    record_audit(
        db,
        "party.created",
        organization_id=principal.organization_id,
        user_id=principal.user_id,
        resource_type="party",
        resource_id=party.id,
        details={"name": party.name, "party_type": party.party_type},
    )
    db.commit()
    db.refresh(party)
    return party


@router.put("/parties/{party_id}", response_model=PartyOut)
def update_party(
    party_id: str,
    data: PartyUpdate,
    principal: CurrentPrincipal = Depends(require_roles(*MANAGE_ROLES)),
    db: Session = Depends(get_db),
):
    party = (
        db.query(Party)
        .filter(Party.id == party_id, Party.organization_id == principal.organization_id)
        .one_or_none()
    )
    if party is None:
        raise HTTPException(status_code=404, detail="主体不存在")
    values = data.model_dump(exclude_none=True)
    if values:
        duplicate = db.query(Party).filter(
            Party.id != party.id,
            Party.organization_id == principal.organization_id,
            Party.party_type == values.get("party_type", party.party_type),
            Party.name == values.get("name", party.name),
        ).first()
        if duplicate:
            raise HTTPException(status_code=409, detail="同类型主体已存在")
        for key, value in values.items():
            setattr(party, key, value)
    record_audit(
        db,
        "party.updated",
        organization_id=principal.organization_id,
        user_id=principal.user_id,
        resource_type="party",
        resource_id=party.id,
        details={"fields": list(values)},
    )
    db.commit()
    db.refresh(party)
    return party


def _get_party(db: Session, principal: CurrentPrincipal, party_id: str) -> Party:
    party = (
        db.query(Party)
        .filter(Party.id == party_id, Party.organization_id == principal.organization_id, Party.status == "active")
        .one_or_none()
    )
    if party is None:
        raise HTTPException(status_code=404, detail="主体不存在")
    return party


@router.get("/parties/{party_id}/contacts", response_model=list[ContactOut])
def list_contacts(
    party_id: str,
    principal: CurrentPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    party = _get_party(db, principal, party_id)
    return [contact for contact in party.contacts if contact.status == "active"]


@router.post("/parties/{party_id}/contacts", response_model=ContactOut, status_code=201)
def create_contact(
    party_id: str,
    data: ContactCreate,
    principal: CurrentPrincipal = Depends(require_roles(*MANAGE_ROLES)),
    db: Session = Depends(get_db),
):
    _get_party(db, principal, party_id)
    if data.is_primary:
        db.query(Contact).filter(
            Contact.party_id == party_id, Contact.organization_id == principal.organization_id
        ).update({Contact.is_primary: False}, synchronize_session=False)
    contact = Contact(
        organization_id=principal.organization_id,
        party_id=party_id,
        **data.model_dump(),
    )
    db.add(contact)
    db.flush()
    record_audit(
        db,
        "contact.created",
        organization_id=principal.organization_id,
        user_id=principal.user_id,
        resource_type="party",
        resource_id=party_id,
        details={"contact_id": contact.id},
    )
    db.commit()
    db.refresh(contact)
    return contact


@router.put("/parties/{party_id}/contacts/{contact_id}", response_model=ContactOut)
def update_contact(
    party_id: str,
    contact_id: str,
    data: ContactUpdate,
    principal: CurrentPrincipal = Depends(require_roles(*MANAGE_ROLES)),
    db: Session = Depends(get_db),
):
    _get_party(db, principal, party_id)
    contact = (
        db.query(Contact)
        .filter(
            Contact.id == contact_id,
            Contact.party_id == party_id,
            Contact.organization_id == principal.organization_id,
        )
        .one_or_none()
    )
    if contact is None:
        raise HTTPException(status_code=404, detail="联系人不存在")
    values = data.model_dump(exclude_none=True)
    if values.get("is_primary"):
        db.query(Contact).filter(
            Contact.party_id == party_id,
            Contact.id != contact.id,
            Contact.organization_id == principal.organization_id,
        ).update({Contact.is_primary: False}, synchronize_session=False)
    for key, value in values.items():
        setattr(contact, key, value)
    record_audit(
        db,
        "contact.updated",
        organization_id=principal.organization_id,
        user_id=principal.user_id,
        resource_type="party",
        resource_id=party_id,
        details={"contact_id": contact.id, "fields": list(values)},
    )
    db.commit()
    db.refresh(contact)
    return contact


@router.get("/contracts/{contract_id}/parties", response_model=list[ContractPartyOut])
def list_contract_parties(
    contract_id: str,
    principal: CurrentPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    contract = _get_contract(db, principal, contract_id)
    links = (
        db.query(ContractParty)
        .join(Party, ContractParty.party_id == Party.id)
        .filter(
            ContractParty.contract_id == contract.id,
            Party.organization_id == principal.organization_id,
        )
        .order_by(ContractParty.role, ContractParty.created_at)
        .all()
    )
    return [_party_link_out(link) for link in links]


@router.post("/contracts/{contract_id}/parties", response_model=ContractPartyOut, status_code=201)
def link_contract_party(
    contract_id: str,
    data: ContractPartyLinkCreate,
    principal: CurrentPrincipal = Depends(require_roles(*MANAGE_ROLES)),
    db: Session = Depends(get_db),
):
    contract = _get_contract(db, principal, contract_id)
    party = _get_party(db, principal, data.party_id)
    if data.role in {"party_a", "party_b"} and db.query(ContractParty).filter(
        ContractParty.contract_id == contract.id, ContractParty.role == data.role
    ).first():
        raise HTTPException(status_code=409, detail=f"合同已关联{data.role}主体")
    duplicate = db.query(ContractParty).filter(
        ContractParty.contract_id == contract.id,
        ContractParty.party_id == party.id,
        ContractParty.role == data.role,
    ).first()
    if duplicate:
        raise HTTPException(status_code=409, detail="该主体已关联到合同")
    link = ContractParty(contract_id=contract.id, party_id=party.id, **data.model_dump(exclude={"party_id"}))
    db.add(link)
    db.flush()
    record_audit(
        db,
        "contract.party_linked",
        organization_id=principal.organization_id,
        user_id=principal.user_id,
        resource_type="contract",
        resource_id=contract.id,
        details={"party_id": party.id, "link_id": link.id, "role": link.role},
    )
    db.commit()
    db.refresh(link)
    return _party_link_out(link)


@router.delete("/contracts/{contract_id}/parties/{link_id}")
def unlink_contract_party(
    contract_id: str,
    link_id: str,
    principal: CurrentPrincipal = Depends(require_roles(*MANAGE_ROLES)),
    db: Session = Depends(get_db),
):
    contract = _get_contract(db, principal, contract_id)
    link = db.query(ContractParty).filter(
        ContractParty.id == link_id, ContractParty.contract_id == contract.id
    ).one_or_none()
    if link is None:
        raise HTTPException(status_code=404, detail="合同主体关联不存在")
    db.delete(link)
    record_audit(
        db,
        "contract.party_unlinked",
        organization_id=principal.organization_id,
        user_id=principal.user_id,
        resource_type="contract",
        resource_id=contract.id,
        details={"party_id": link.party_id, "link_id": link.id},
    )
    db.commit()
    return {"message": "主体关联已解除"}


@router.get("/contracts/{contract_id}/tasks", response_model=list[FulfillmentTaskOut])
def list_tasks(
    contract_id: str,
    status: str | None = Query(default=None, pattern=r"^(pending|in_progress|completed|cancelled)$"),
    overdue_only: bool = False,
    principal: CurrentPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    contract = _get_contract(db, principal, contract_id)
    query = db.query(FulfillmentTask).filter(
        FulfillmentTask.contract_id == contract.id,
        FulfillmentTask.organization_id == principal.organization_id,
    )
    if status:
        query = query.filter(FulfillmentTask.status == status)
    tasks = query.order_by(FulfillmentTask.due_at.asc(), FulfillmentTask.created_at.asc()).all()
    return [task for task in tasks if not overdue_only or task_is_overdue(task)]


@router.post("/contracts/{contract_id}/tasks", response_model=FulfillmentTaskOut, status_code=201)
def create_task(
    contract_id: str,
    data: FulfillmentTaskCreate,
    principal: CurrentPrincipal = Depends(require_roles(*MANAGE_ROLES)),
    db: Session = Depends(get_db),
):
    contract = _get_contract(db, principal, contract_id)
    due_at, remind_at = validate_schedule(data.due_at, data.remind_at)
    ensure_assignee(db, principal.organization_id, data.assignee_id)
    task = FulfillmentTask(
        organization_id=principal.organization_id,
        contract_id=contract.id,
        created_by=principal.user_id,
        updated_by=principal.user_id,
        due_at=due_at,
        remind_at=remind_at,
        **data.model_dump(exclude={"due_at", "remind_at"}),
    )
    db.add(task)
    db.flush()
    record_audit(
        db,
        "contract.task_created",
        organization_id=principal.organization_id,
        user_id=principal.user_id,
        resource_type="contract",
        resource_id=contract.id,
        details={"task_id": task.id, "status": task.status},
    )
    db.commit()
    db.refresh(task)
    return _task_out(task)


@router.patch("/contracts/{contract_id}/tasks/{task_id}", response_model=FulfillmentTaskOut)
def update_task(
    contract_id: str,
    task_id: str,
    data: FulfillmentTaskUpdate,
    principal: CurrentPrincipal = Depends(require_roles(*MANAGE_ROLES)),
    db: Session = Depends(get_db),
):
    contract = _get_contract(db, principal, contract_id)
    task = db.query(FulfillmentTask).filter(
        FulfillmentTask.id == task_id,
        FulfillmentTask.contract_id == contract.id,
        FulfillmentTask.organization_id == principal.organization_id,
    ).one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="履约任务不存在")
    values = data.model_dump(exclude_unset=True)
    target_status = values.get("status", task.status)
    validate_transition(task.status, target_status)
    due_at = values.get("due_at", task.due_at)
    remind_at = values.get("remind_at", task.remind_at)
    due_date_was_changed = "due_at" in values
    due_at, remind_at = validate_schedule(
        due_at,
        remind_at,
        allow_past_due=(
            not due_date_was_changed and as_utc(task.due_at) < datetime.now(timezone.utc)
        ),
    )
    ensure_assignee(db, principal.organization_id, values.get("assignee_id", task.assignee_id))
    transitioned_to_completed = task.status != "completed" and target_status == "completed"
    if transitioned_to_completed and "completed_at" not in values:
        values["completed_at"] = datetime.now(timezone.utc)
    if target_status != "completed" and values.get("completed_at") is not None:
        raise HTTPException(status_code=422, detail="只有已完成任务可以填写完成时间")
    if target_status == "completed" and values.get("completed_at", task.completed_at) is None:
        raise HTTPException(status_code=422, detail="已完成任务必须填写完成时间")
    values.pop("due_at", None)
    values.pop("remind_at", None)
    for key, value in values.items():
        setattr(task, key, value)
    task.due_at = due_at
    task.remind_at = remind_at
    task.updated_by = principal.user_id
    if target_status == "completed" and task.completed_by is None:
        task.completed_by = principal.user_id
    if target_status != "completed":
        task.completed_by = None
        task.completed_at = None
    record_audit(
        db,
        "contract.task_updated",
        organization_id=principal.organization_id,
        user_id=principal.user_id,
        resource_type="contract",
        resource_id=contract.id,
        details={"task_id": task.id, "status": task.status, "fields": list(data.model_dump(exclude_unset=True))},
    )
    db.commit()
    db.refresh(task)
    return _task_out(task)
