"""Organization-scoped contract ledger, file version, and import APIs."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import asc, desc
from sqlalchemy.orm import Session

from config import settings
from core.security import CurrentPrincipal, as_utc, get_current_principal, require_roles
from database import get_db
from models.contract import Contract, ContractFile, ContractImportJob, FileVersion
from schemas.contracts import (
    ContractCreate,
    ContractFileOut,
    ContractImportConfirmOut,
    ContractImportPreview,
    ContractOut,
    FileVersionOut,
    PagedContracts,
)
from services.audit_service import record_audit
from services.file_service import (
    mime_type_for,
    remove_storage_key,
    save_upload,
    storage_path,
    validate_extension,
)
from services.import_service import commit_rows, parse_import_file, validate_rows

router = APIRouter(prefix="/api/v1/contracts", tags=["contracts"])
MANAGE_ROLES = ("system_admin", "org_admin", "contract_manager")
SORT_COLUMNS = {
    "updated_at": Contract.updated_at,
    "created_at": Contract.created_at,
    "name": Contract.name,
    "contract_no": Contract.contract_no,
    "amount": Contract.amount,
    "risk_level": Contract.risk_level,
    "status": Contract.status,
}


def _page_contracts(
    db: Session,
    principal: CurrentPrincipal,
    page: int,
    page_size: int,
    search: str | None,
    status: str | None,
    sort_by: str,
    sort_order: str,
    include_deleted: bool,
) -> PagedContracts:
    query = db.query(Contract).filter(Contract.organization_id == principal.organization_id)
    if not include_deleted:
        query = query.filter(Contract.deleted_at.is_(None))
    if search and search.strip():
        term = search.strip()
        query = query.filter(
            Contract.name.contains(term, autoescape=True)
            | Contract.contract_no.contains(term, autoescape=True)
            | Contract.party_a_name.contains(term, autoescape=True)
            | Contract.party_b_name.contains(term, autoescape=True)
        )
    if status:
        query = query.filter(Contract.status == status)
    column = SORT_COLUMNS[sort_by]
    ordering = asc(column) if sort_order == "asc" else desc(column)
    total = query.count()
    items = query.order_by(ordering, Contract.id.asc()).offset((page - 1) * page_size).limit(page_size).all()
    return PagedContracts(items=items, total=total, page=page, page_size=page_size)


@router.get("", response_model=PagedContracts)
def list_contracts(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None, max_length=200),
    status: str | None = Query(default=None, max_length=32),
    sort_by: str = Query(default="updated_at", pattern=r"^(updated_at|created_at|name|contract_no|amount|risk_level|status)$"),
    sort_order: str = Query(default="desc", pattern=r"^(asc|desc)$"),
    principal: CurrentPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    return _page_contracts(
        db, principal, page, page_size, search, status, sort_by, sort_order, include_deleted=False
    )


@router.get("/recycle-bin", response_model=PagedContracts)
def list_recycle_bin(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None, max_length=200),
    sort_by: str = Query(default="deleted_at", pattern=r"^(deleted_at|updated_at|created_at|name|contract_no)$"),
    sort_order: str = Query(default="desc", pattern=r"^(asc|desc)$"),
    principal: CurrentPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    query = db.query(Contract).filter(
        Contract.organization_id == principal.organization_id, Contract.deleted_at.isnot(None)
    )
    if search and search.strip():
        term = search.strip()
        query = query.filter(
            Contract.name.contains(term, autoescape=True)
            | Contract.contract_no.contains(term, autoescape=True)
        )
    columns = {**SORT_COLUMNS, "deleted_at": Contract.deleted_at}
    column = columns[sort_by]
    ordering = asc(column) if sort_order == "asc" else desc(column)
    total = query.count()
    items = query.order_by(ordering, Contract.id.asc()).offset((page - 1) * page_size).limit(page_size).all()
    return PagedContracts(items=items, total=total, page=page, page_size=page_size)


@router.post("", response_model=ContractOut, status_code=201)
def create_contract(
    data: ContractCreate,
    principal: CurrentPrincipal = Depends(require_roles(*MANAGE_ROLES)),
    db: Session = Depends(get_db),
):
    if data.contract_no:
        duplicate = db.query(Contract).filter(
            Contract.organization_id == principal.organization_id,
            Contract.contract_no == data.contract_no,
        ).first()
        if duplicate and duplicate.deleted_at is None:
            raise HTTPException(status_code=409, detail="合同编号已存在")
        if duplicate:
            raise HTTPException(status_code=409, detail="回收站中已有相同合同编号，请先恢复或处理原记录")
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
        details={"contract_no": contract.contract_no, "source": "manual"},
    )
    db.commit()
    db.refresh(contract)
    return contract


def _get_contract(
    db: Session, principal: CurrentPrincipal, contract_id: str, include_deleted: bool = False
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


@router.get("/{contract_id}", response_model=ContractOut)
def get_contract(
    contract_id: str,
    principal: CurrentPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    return _get_contract(db, principal, contract_id)


@router.delete("/{contract_id}")
def delete_contract(
    contract_id: str,
    principal: CurrentPrincipal = Depends(require_roles(*MANAGE_ROLES)),
    db: Session = Depends(get_db),
):
    contract = _get_contract(db, principal, contract_id)
    contract.deleted_at = datetime.now(timezone.utc)
    contract.updated_by = principal.user_id
    record_audit(
        db,
        "contract.deleted",
        organization_id=principal.organization_id,
        user_id=principal.user_id,
        resource_type="contract",
        resource_id=contract.id,
    )
    db.commit()
    return {"message": "合同已移入回收站", "id": contract.id}


@router.post("/{contract_id}/restore", response_model=ContractOut)
def restore_contract(
    contract_id: str,
    principal: CurrentPrincipal = Depends(require_roles(*MANAGE_ROLES)),
    db: Session = Depends(get_db),
):
    contract = _get_contract(db, principal, contract_id, include_deleted=True)
    if contract.deleted_at is None:
        return contract
    contract.deleted_at = None
    contract.updated_by = principal.user_id
    record_audit(
        db,
        "contract.restored",
        organization_id=principal.organization_id,
        user_id=principal.user_id,
        resource_type="contract",
        resource_id=contract.id,
    )
    db.commit()
    db.refresh(contract)
    return contract


def _get_file_version(
    db: Session,
    principal: CurrentPrincipal,
    contract_id: str,
    file_id: str,
    version_id: str,
) -> FileVersion:
    version = (
        db.query(FileVersion)
        .join(ContractFile, FileVersion.contract_file_id == ContractFile.id)
        .join(Contract, ContractFile.contract_id == Contract.id)
        .filter(
            FileVersion.id == version_id,
            ContractFile.id == file_id,
            Contract.id == contract_id,
            Contract.organization_id == principal.organization_id,
            Contract.deleted_at.is_(None),
            ContractFile.deleted_at.is_(None),
            FileVersion.deleted_at.is_(None),
        )
        .one_or_none()
    )
    if version is None:
        raise HTTPException(status_code=404, detail="文件版本不存在")
    return version


def _version_out(contract_id: str, version: FileVersion) -> FileVersionOut:
    prefix = f"/api/v1/contracts/{contract_id}/files/{version.contract_file_id}/versions/{version.id}"
    return FileVersionOut(
        id=version.id,
        contract_file_id=version.contract_file_id,
        version_no=version.version_no,
        original_filename=version.original_filename,
        mime_type=version.mime_type,
        size_bytes=version.size_bytes,
        sha256=version.sha256,
        page_count=version.page_count,
        uploaded_at=version.uploaded_at,
        is_current=version.is_current,
        download_url=f"{prefix}/download",
        preview_url=f"{prefix}/preview",
    )


@router.get("/{contract_id}/files", response_model=list[ContractFileOut])
def list_contract_files(
    contract_id: str,
    principal: CurrentPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    _get_contract(db, principal, contract_id)
    files = (
        db.query(ContractFile)
        .filter(ContractFile.contract_id == contract_id, ContractFile.deleted_at.is_(None))
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
                _version_out(contract_id, version)
                for version in sorted(
                    (item for item in contract_file.versions if item.deleted_at is None),
                    key=lambda item: item.version_no,
                    reverse=True,
                )
            ],
        )
        for contract_file in files
    ]


@router.post("/{contract_id}/files", response_model=FileVersionOut, status_code=201)
async def upload_contract_file(
    contract_id: str,
    file: UploadFile = File(...),
    purpose: str = Form(default="original", max_length=50),
    principal: CurrentPrincipal = Depends(require_roles(*MANAGE_ROLES)),
    db: Session = Depends(get_db),
):
    contract = _get_contract(db, principal, contract_id)
    extension = validate_extension(file.filename)
    storage_key = None
    committed = False
    try:
        storage_key, size, sha256 = await save_upload(file, extension)
        if size == 0:
            raise HTTPException(status_code=400, detail="不能上传空文件")
        duplicate = (
            db.query(FileVersion)
            .join(ContractFile, FileVersion.contract_file_id == ContractFile.id)
            .join(Contract, ContractFile.contract_id == Contract.id)
            .filter(
                Contract.organization_id == principal.organization_id,
                FileVersion.deleted_at.is_(None),
                FileVersion.sha256 == sha256,
            )
            .first()
        )
        if duplicate:
            raise HTTPException(status_code=409, detail="文件内容已存在，禁止重复上传")
        contract_file = (
            db.query(ContractFile)
            .filter(
                ContractFile.contract_id == contract.id,
                ContractFile.purpose == purpose,
                ContractFile.deleted_at.is_(None),
            )
            .one_or_none()
        )
        if contract_file is None:
            contract_file = ContractFile(contract_id=contract.id, purpose=purpose)
            db.add(contract_file)
            db.flush()
        version_no = (
            db.query(FileVersion.version_no)
            .filter(FileVersion.contract_file_id == contract_file.id)
            .order_by(FileVersion.version_no.desc())
            .first()
        )
        next_version = (version_no[0] if version_no else 0) + 1
        db.query(FileVersion).filter(
            FileVersion.contract_file_id == contract_file.id, FileVersion.is_current.is_(True)
        ).update({FileVersion.is_current: False}, synchronize_session=False)
        version = FileVersion(
            id=str(uuid.uuid4()),
            contract_file_id=contract_file.id,
            version_no=next_version,
            original_filename=Path(file.filename or "文件").name,
            storage_key=storage_key,
            mime_type=mime_type_for(file.filename),
            size_bytes=size,
            sha256=sha256,
            uploaded_by=principal.user_id,
            is_current=True,
        )
        db.add(version)
        db.flush()
        contract_file.current_version_id = version.id
        contract.updated_by = principal.user_id
        record_audit(
            db,
            "contract.file_uploaded",
            organization_id=principal.organization_id,
            user_id=principal.user_id,
            resource_type="file_version",
            resource_id=version.id,
            details={"contract_id": contract.id, "version_no": next_version, "sha256": sha256},
        )
        db.commit()
        committed = True
        return _version_out(contract.id, version)
    except Exception:
        db.rollback()
        if not committed:
            remove_storage_key(storage_key)
        raise


@router.get("/{contract_id}/files/{file_id}/versions", response_model=list[FileVersionOut])
def list_file_versions(
    contract_id: str,
    file_id: str,
    principal: CurrentPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    _get_contract(db, principal, contract_id)
    contract_file = (
        db.query(ContractFile)
        .filter(
            ContractFile.id == file_id,
            ContractFile.contract_id == contract_id,
            ContractFile.deleted_at.is_(None),
        )
        .one_or_none()
    )
    if contract_file is None:
        raise HTTPException(status_code=404, detail="文件不存在")
    return [
        _version_out(contract_id, version)
        for version in sorted(
            (item for item in contract_file.versions if item.deleted_at is None),
            key=lambda item: item.version_no,
            reverse=True,
        )
    ]


def _file_response(version: FileVersion, inline: bool) -> FileResponse:
    path = storage_path(version.storage_key)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="文件实体不存在")
    disposition = "inline" if inline else "attachment"
    filename = quote(version.original_filename, safe="")
    return FileResponse(
        path,
        media_type=version.mime_type,
        headers={"Content-Disposition": f"{disposition}; filename*=UTF-8''{filename}"},
    )


@router.get("/{contract_id}/files/{file_id}/versions/{version_id}/download")
def download_file_version(
    contract_id: str,
    file_id: str,
    version_id: str,
    principal: CurrentPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    version = _get_file_version(db, principal, contract_id, file_id, version_id)
    return _file_response(version, inline=False)


@router.get("/{contract_id}/files/{file_id}/versions/{version_id}/preview")
def preview_file_version(
    contract_id: str,
    file_id: str,
    version_id: str,
    principal: CurrentPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    version = _get_file_version(db, principal, contract_id, file_id, version_id)
    return _file_response(version, inline=True)


def _get_import_job(db: Session, principal: CurrentPrincipal, job_id: str) -> ContractImportJob:
    job = (
        db.query(ContractImportJob)
        .filter(
            ContractImportJob.id == job_id,
            ContractImportJob.organization_id == principal.organization_id,
        )
        .one_or_none()
    )
    if job is None:
        raise HTTPException(status_code=404, detail="导入任务不存在")
    if as_utc(job.expires_at) and as_utc(job.expires_at) < datetime.now(timezone.utc) and job.status != "confirmed":
        raise HTTPException(status_code=410, detail="导入任务已过期")
    return job


def _import_out(job: ContractImportJob) -> ContractImportPreview:
    rows = json.loads(job.rows_json or "[]")
    return ContractImportPreview(
        id=job.id,
        original_filename=job.original_filename,
        file_format=job.file_format,
        columns=json.loads(job.columns_json or "[]"),
        sample_rows=rows[:10],
        row_count=job.row_count,
        status=job.status,
        validation=json.loads(job.validation_json or "{}"),
        expires_at=job.expires_at,
    )


@router.post("/imports", response_model=ContractImportPreview, status_code=201)
async def create_import_job(
    file: UploadFile = File(...),
    principal: CurrentPrincipal = Depends(require_roles(*MANAGE_ROLES)),
    db: Session = Depends(get_db),
):
    content = await file.read(settings.max_file_size_bytes + 1)
    if len(content) > settings.max_file_size_bytes:
        raise HTTPException(status_code=413, detail="导入文件超过大小限制")
    file_format, columns, rows = parse_import_file(file.filename or "contracts.csv", content)
    job = ContractImportJob(
        id=str(uuid.uuid4()),
        organization_id=principal.organization_id,
        created_by=principal.user_id,
        original_filename=Path(file.filename or "contracts").name,
        file_format=file_format,
        rows_json=json.dumps(rows, ensure_ascii=False),
        columns_json=json.dumps(columns, ensure_ascii=False),
        validation_json=json.dumps({}, ensure_ascii=False),
        status="uploaded",
        row_count=len(rows),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    try:
        db.add(job)
        db.commit()
        db.refresh(job)
    except Exception:
        db.rollback()
        raise HTTPException(status_code=500, detail="导入任务创建失败")
    record_audit(
        db,
        "contract.import_uploaded",
        organization_id=principal.organization_id,
        user_id=principal.user_id,
        resource_type="contract_import",
        resource_id=job.id,
        details={"filename": job.original_filename, "row_count": job.row_count},
    )
    db.commit()
    return _import_out(job)


@router.get("/imports/{job_id}", response_model=ContractImportPreview)
def get_import_preview(
    job_id: str,
    principal: CurrentPrincipal = Depends(require_roles(*MANAGE_ROLES)),
    db: Session = Depends(get_db),
):
    return _import_out(_get_import_job(db, principal, job_id))


@router.post("/imports/{job_id}/validate", response_model=ContractImportPreview)
def validate_import(
    job_id: str,
    principal: CurrentPrincipal = Depends(require_roles(*MANAGE_ROLES)),
    db: Session = Depends(get_db),
):
    job = _get_import_job(db, principal, job_id)
    if job.status == "confirmed":
        raise HTTPException(status_code=409, detail="导入任务已经确认")
    validation = validate_rows(db, job)
    job.validation_json = json.dumps(validation, ensure_ascii=False)
    job.status = "validated"
    job.validated_at = datetime.now(timezone.utc)
    db.commit()
    return _import_out(job)


@router.post("/imports/{job_id}/confirm", response_model=ContractImportConfirmOut)
def confirm_import(
    job_id: str,
    principal: CurrentPrincipal = Depends(require_roles(*MANAGE_ROLES)),
    db: Session = Depends(get_db),
):
    job = _get_import_job(db, principal, job_id)
    validation = json.loads(job.validation_json or "{}")
    if job.status != "validated" or not validation.get("valid"):
        raise HTTPException(status_code=409, detail="请先完成无错误的导入校验")
    try:
        contracts = commit_rows(db, job, principal.user_id)
        job.status = "confirmed"
        job.confirmed_at = datetime.now(timezone.utc)
        record_audit(
            db,
            "contract.import_confirmed",
            organization_id=principal.organization_id,
            user_id=principal.user_id,
            resource_type="contract_import",
            resource_id=job.id,
            details={"created_count": len(contracts)},
        )
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="导入确认失败，未写入任何合同") from exc
    return ContractImportConfirmOut(
        job_id=job.id, created_count=len(contracts), contract_ids=[contract.id for contract in contracts]
    )
