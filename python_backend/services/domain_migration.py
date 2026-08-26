"""Idempotent migration from legacy documents to Stage 2 domain records."""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from config import DEEPSEEK_MODEL
from models.contract import (
    AnalysisRun,
    AnalysisTemplateVersion,
    Contract,
    ContractFile,
    FileVersion,
    Organization,
    User,
)
from models.document import AnalysisResult, AnalysisTemplate, Document

logger = logging.getLogger("contract_analyzer.domain_migration")
MIGRATION_NAMESPACE = uuid.UUID("0e8c3e46-6b22-4f5e-b7c5-c3eab32963f1")
LEGACY_ORGANIZATION_CODE = "legacy"
LEGACY_USERNAME = "legacy-migration"


def _stable_id(kind: str, value: str) -> str:
    return str(uuid.uuid5(MIGRATION_NAMESPACE, f"{kind}:{value}"))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _contract_status(document_status: str | None) -> str:
    if document_status in {"done", "ocr_done"}:
        return "active"
    return "draft"


def _filename_stem(filename: str | None) -> str:
    name = Path(filename or "").stem.strip()
    return name or "未命名合同"


def _get_or_create_legacy_identity(db: Session) -> tuple[Organization, User]:
    organization = (
        db.query(Organization).filter(Organization.code == LEGACY_ORGANIZATION_CODE).one_or_none()
    )
    now = _now()
    if organization is None:
        organization = Organization(
            id=_stable_id("organization", LEGACY_ORGANIZATION_CODE),
            name="历史数据组织",
            code=LEGACY_ORGANIZATION_CODE,
            metadata_json=json.dumps({"source": "stage2_legacy_migration"}, ensure_ascii=False),
            created_at=now,
            updated_at=now,
        )
        db.add(organization)
        db.flush()

    user = db.query(User).filter(User.username == LEGACY_USERNAME).one_or_none()
    if user is None:
        user = User(
            id=_stable_id("user", LEGACY_USERNAME),
            organization_id=organization.id,
            username=LEGACY_USERNAME,
            display_name="历史数据迁移",
            status="active",
            created_at=now,
            updated_at=now,
        )
        db.add(user)
        db.flush()
    return organization, user


def _migrate_template_versions(db: Session, migration_user: User) -> dict[tuple[str, int], str]:
    versions: dict[tuple[str, int], str] = {}
    templates = db.query(AnalysisTemplate).order_by(AnalysisTemplate.created_at.asc()).all()
    for template in templates:
        version = (
            template.version if isinstance(template.version, int) and template.version > 0 else 1
        )
        key = (template.id, version)
        version_row = (
            db.query(AnalysisTemplateVersion)
            .filter(
                AnalysisTemplateVersion.template_id == template.id,
                AnalysisTemplateVersion.version == version,
            )
            .one_or_none()
        )
        if version_row is None:
            created_at = template.created_at or _now()
            version_row = AnalysisTemplateVersion(
                id=_stable_id("template-version", f"{template.id}:{version}"),
                template_id=template.id,
                version=version,
                fields_json=template.fields_json or "[]",
                analysis_focus=template.analysis_focus or "",
                review_enabled=bool(template.review_enabled),
                review_instructions=template.review_instructions or "",
                model_name=DEEPSEEK_MODEL,
                prompt_version=f"legacy-template-v{version}",
                status="published",
                created_by=migration_user.id,
                created_at=created_at,
                published_at=created_at,
            )
            db.add(version_row)
            db.flush()
        versions[key] = version_row.id
    return versions


def _migrate_contract(
    db: Session,
    document: Document,
    organization: Organization,
    migration_user: User,
    template_version_ids: dict[tuple[str, int], str],
    upload_dir: Path,
    report: dict,
) -> tuple[Contract, FileVersion]:
    contract = db.query(Contract).filter(Contract.legacy_document_id == document.id).one_or_none()
    created_at = document.created_at or _now()
    updated_at = document.updated_at or created_at
    metadata = {
        "legacy_document_id": document.id,
        "legacy_status": document.status,
        "legacy_original_filename": document.original_filename,
        "legacy_template_id": document.analysis_template_id,
        "legacy_template_name": document.analysis_template_name,
        "legacy_template_version": document.analysis_template_version,
        "migration_note": "历史字段未做不可靠推断，待人工补录结构化主数据",
    }
    if contract is None:
        contract = Contract(
            id=_stable_id("contract", document.id),
            organization_id=organization.id,
            legacy_document_id=document.id,
            name=_filename_stem(document.original_filename),
            category=document.analysis_template_name,
            status=_contract_status(document.status),
            risk_level="medium",
            source="legacy",
            metadata_json=json.dumps(metadata, ensure_ascii=False),
            created_by=migration_user.id,
            updated_by=migration_user.id,
            created_at=created_at,
            updated_at=updated_at,
        )
        db.add(contract)
        db.flush()

    contract_file = (
        db.query(ContractFile)
        .filter(ContractFile.contract_id == contract.id, ContractFile.purpose == "original")
        .one_or_none()
    )
    if contract_file is None:
        contract_file = ContractFile(
            id=_stable_id("contract-file", document.id),
            contract_id=contract.id,
            purpose="original",
            created_at=created_at,
            updated_at=updated_at,
        )
        db.add(contract_file)
        db.flush()

    source_path = upload_dir / document.stored_filename
    sha256 = _hash_file(source_path)
    if sha256 is None:
        report["missing_files"].append(
            {"document_id": document.id, "storage_key": document.stored_filename}
        )
    else:
        report["hash_to_documents"][sha256].append(document.id)

    file_version = (
        db.query(FileVersion)
        .filter(
            FileVersion.contract_file_id == contract_file.id,
            FileVersion.version_no == 1,
        )
        .one_or_none()
    )
    if file_version is None:
        file_version = FileVersion(
            id=_stable_id("file-version", document.id),
            contract_file_id=contract_file.id,
            version_no=1,
            original_filename=document.original_filename,
            storage_key=document.stored_filename,
            mime_type="application/pdf",
            size_bytes=source_path.stat().st_size if source_path.is_file() else document.file_size,
            sha256=sha256,
            page_count=document.page_count,
            uploaded_by=migration_user.id,
            uploaded_at=created_at,
            is_current=True,
        )
        db.add(file_version)
        db.flush()
    elif sha256 and not file_version.sha256:
        file_version.sha256 = sha256
        file_version.size_bytes = source_path.stat().st_size
        file_version.page_count = document.page_count
    contract_file.current_version_id = file_version.id
    return contract, file_version


def _migrate_analysis_run(
    db: Session,
    document: Document,
    contract: Contract,
    file_version: FileVersion,
    migration_user: User,
    template_version_ids: dict[tuple[str, int], str],
    results: list[AnalysisResult],
    report: dict,
) -> None:
    if not results:
        return
    run_id = _stable_id("analysis-run", document.id)
    run = db.get(AnalysisRun, run_id)
    first_result = results[0]
    template_version = first_result.template_version or document.analysis_template_version or 1
    template_version_id = template_version_ids.get((first_result.template_id, template_version))
    if run is None:
        output_tokens = sum(result.tokens_used or 0 for result in results)
        created_at = document.created_at or _now()
        run = AnalysisRun(
            id=run_id,
            contract_id=contract.id,
            file_version_id=file_version.id,
            task_type="legacy_analysis",
            status="succeeded",
            requested_by=migration_user.id,
            started_at=created_at,
            finished_at=document.updated_at or created_at,
            provider_name="deepseek",
            model_name=DEEPSEEK_MODEL,
            prompt_version=f"legacy-template-v{template_version}",
            template_version_id=template_version_id,
            input_chars=len(document.ocr_text or ""),
            output_tokens=output_tokens or None,
            created_at=created_at,
        )
        db.add(run)
        db.flush()
    for result in results:
        if result.analysis_run_id != run.id:
            result.analysis_run_id = run.id
    report["analysis_run_mappings"].append(
        {"document_id": document.id, "analysis_run_id": run.id, "result_count": len(results)}
    )


def _write_report(report: dict, report_path: Path | None) -> None:
    if report_path is None:
        return
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def migrate_legacy_data(
    db: Session,
    upload_dir: Path,
    report_path: Path | None = None,
) -> dict:
    """Migrate legacy rows once and return an auditable reconciliation report."""
    organization, migration_user = _get_or_create_legacy_identity(db)
    template_version_ids = _migrate_template_versions(db, migration_user)
    report = {
        "migration": "stage2_legacy_document_to_contract",
        "generated_at": _now().isoformat(),
        "source_counts": {
            "documents": db.query(Document).count(),
            "analysis_results": db.query(AnalysisResult).count(),
            "analysis_templates": db.query(AnalysisTemplate).count(),
        },
        "target_counts": {},
        "missing_files": [],
        "duplicate_files": [],
        "hash_to_documents": defaultdict(list),
        "contract_mappings": [],
        "analysis_run_mappings": [],
    }
    for document in db.query(Document).order_by(Document.created_at.asc(), Document.id.asc()).all():
        results = (
            db.query(AnalysisResult)
            .filter(AnalysisResult.document_id == document.id)
            .order_by(AnalysisResult.created_at.asc(), AnalysisResult.id.asc())
            .all()
        )
        contract, file_version = _migrate_contract(
            db,
            document,
            organization,
            migration_user,
            template_version_ids,
            upload_dir,
            report,
        )
        _migrate_analysis_run(
            db,
            document,
            contract,
            file_version,
            migration_user,
            template_version_ids,
            results,
            report,
        )
        report["contract_mappings"].append(
            {
                "document_id": document.id,
                "contract_id": contract.id,
                "file_version_id": file_version.id,
            }
        )

    report["duplicate_files"] = [
        {"sha256": digest, "document_ids": ids}
        for digest, ids in report["hash_to_documents"].items()
        if len(ids) > 1
    ]
    report["hash_to_documents"] = dict(report["hash_to_documents"])
    db.commit()
    report["target_counts"] = {
        "organizations": db.query(Organization).count(),
        "users": db.query(User).count(),
        "contracts": db.query(Contract).count(),
        "contract_files": db.query(ContractFile).count(),
        "file_versions": db.query(FileVersion).count(),
        "analysis_template_versions": db.query(AnalysisTemplateVersion).count(),
        "analysis_runs": db.query(AnalysisRun).count(),
    }
    _write_report(report, report_path)
    logger.info(
        "Legacy migration complete documents=%s contracts=%s analysis_runs=%s missing_files=%s",
        report["source_counts"]["documents"],
        report["target_counts"]["contracts"],
        report["target_counts"]["analysis_runs"],
        len(report["missing_files"]),
    )
    return report
