"""Organization-scoped structured analysis, evidence, risk, and review APIs."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from core.security import CurrentPrincipal, get_current_principal, require_roles
from database import get_db
from models.contract import AnalysisRisk, AnalysisRun, Contract, StructuredAnalysisResult
from models.document import AnalysisResult
from schemas.structured_analysis import (
    AnalysisRunOut,
    EvidenceOut,
    ReviewDecision,
    RiskOut,
    RiskStatusUpdate,
    StructuredFieldOut,
    StructuredResultCreate,
    StructuredResultOut,
    StructuredRevisionCreate,
)
from services.audit_service import record_audit
from services.risk_service import update_risk
from services.structured_analysis_service import (
    create_result_version,
    get_run_for_organization,
    import_legacy_results,
    review_result,
    submit_for_review,
    validate_run_links,
)

router = APIRouter(prefix="/api/v1", tags=["structured-analysis"])
CREATE_ROLES = ("system_admin", "org_admin", "contract_manager", "reviewer")
REVIEW_ROLES = ("system_admin", "org_admin", "reviewer")


def _json_value(text: str, fallback):
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return fallback


def _result_out(result: StructuredAnalysisResult) -> StructuredResultOut:
    if not result.file_version_id or not result.template_version_id:
        raise HTTPException(status_code=500, detail="结构化结果缺少版本关联")
    return StructuredResultOut(
        id=result.id,
        organization_id=result.organization_id,
        contract_id=result.contract_id,
        analysis_run_id=result.analysis_run_id,
        source_result_id=result.source_result_id,
        file_version_id=result.file_version_id,
        template_version_id=result.template_version_id,
        prompt_type=result.prompt_type,
        version=result.version,
        status=result.status,
        summary=result.summary,
        created_by=result.created_by,
        reviewed_by=result.reviewed_by,
        review_comment=result.review_comment,
        reviewed_at=result.reviewed_at,
        created_at=result.created_at,
        updated_at=result.updated_at,
        fields=[
            StructuredFieldOut(
                id=field.id,
                field_key=field.field_key,
                label=field.label,
                value=_json_value(field.value_json, field.value_text),
                value_text=field.value_text,
                confidence=float(field.confidence) if field.confidence is not None else None,
                position=field.position,
            )
            for field in result.fields
        ],
        evidence=[
            EvidenceOut(
                id=evidence.id,
                file_version_id=evidence.file_version_id,
                page_no=evidence.page_no,
                char_start=evidence.char_start,
                char_end=evidence.char_end,
                quote=evidence.quote,
                locator=_json_value(evidence.locator_json, {}),
                created_at=evidence.created_at,
            )
            for evidence in result.evidence
        ],
        risks=[
            RiskOut(
                id=risk.id,
                evidence_id=risk.evidence_id,
                code=risk.code,
                title=risk.title,
                description=risk.description,
                severity=risk.severity,
                status=risk.status,
                assignee_id=risk.assignee_id,
                remediation_due_at=risk.remediation_due_at,
                remediation_notes=risk.remediation_notes,
                reviewer_comment=risk.reviewer_comment,
                reviewed_by=risk.reviewed_by,
                reviewed_at=risk.reviewed_at,
                closed_by=risk.closed_by,
                closed_at=risk.closed_at,
                closure_comment=risk.closure_comment,
                is_overdue=(
                    risk.status in {"open", "in_progress"}
                    and risk.remediation_due_at is not None
                    and (
                        risk.remediation_due_at.replace(tzinfo=timezone.utc)
                        if risk.remediation_due_at.tzinfo is None
                        else risk.remediation_due_at
                    )
                    < datetime.now(timezone.utc)
                ),
                created_at=risk.created_at,
            )
            for risk in result.risks
        ],
    )


def _latest_results(results: list[StructuredAnalysisResult]) -> list[StructuredAnalysisResult]:
    latest: dict[str, StructuredAnalysisResult] = {}
    for result in sorted(results, key=lambda item: item.version, reverse=True):
        latest.setdefault(result.prompt_type, result)
    return list(latest.values())


def _run_out(db: Session, run: AnalysisRun, contract: Contract) -> AnalysisRunOut:
    file_name = run.file_version.original_filename if run.file_version else None
    template = run.template_version
    template_name = template.template.name if template and template.template else None
    raw_count = (
        db.query(AnalysisResult).filter(AnalysisResult.analysis_run_id == run.id).count()
    )
    return AnalysisRunOut(
        id=run.id,
        contract_id=contract.id,
        contract_name=contract.name,
        contract_no=contract.contract_no,
        file_version_id=run.file_version_id,
        file_name=file_name,
        template_version_id=run.template_version_id,
        template_name=template_name,
        template_version=template.version if template else None,
        task_type=run.task_type,
        status=run.status,
        provider_name=run.provider_name,
        model_name=run.model_name,
        requested_by=run.requested_by,
        started_at=run.started_at,
        finished_at=run.finished_at,
        created_at=run.created_at,
        raw_result_count=raw_count,
        structured_results=[_result_out(item) for item in _latest_results(run.structured_results)],
    )


def _get_result(
    db: Session,
    principal: CurrentPrincipal,
    run_id: str,
    result_id: str,
) -> tuple[AnalysisRun, Contract, StructuredAnalysisResult]:
    run, contract = get_run_for_organization(db, principal.organization_id, run_id)
    result = (
        db.query(StructuredAnalysisResult)
        .filter(
            StructuredAnalysisResult.id == result_id,
            StructuredAnalysisResult.analysis_run_id == run.id,
            StructuredAnalysisResult.organization_id == principal.organization_id,
            StructuredAnalysisResult.contract_id == contract.id,
        )
        .one_or_none()
    )
    if result is None:
        raise HTTPException(status_code=404, detail="结构化结果不存在")
    return run, contract, result


@router.get("/contracts/{contract_id}/analysis-runs", response_model=list[AnalysisRunOut])
def list_contract_analysis_runs(
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
    runs = (
        db.query(AnalysisRun)
        .filter(AnalysisRun.contract_id == contract.id)
        .order_by(AnalysisRun.created_at.desc())
        .limit(100)
        .all()
    )
    return [_run_out(db, run, contract) for run in runs]


@router.get("/analysis-runs/{run_id}", response_model=AnalysisRunOut)
def get_analysis_run(
    run_id: str,
    principal: CurrentPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    run, contract = get_run_for_organization(db, principal.organization_id, run_id)
    return _run_out(db, run, contract)


@router.get(
    "/analysis-runs/{run_id}/structured-results",
    response_model=list[StructuredResultOut],
)
def list_structured_results(
    run_id: str,
    principal: CurrentPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    run, _contract = get_run_for_organization(db, principal.organization_id, run_id)
    results = (
        db.query(StructuredAnalysisResult)
        .filter(
            StructuredAnalysisResult.analysis_run_id == run.id,
            StructuredAnalysisResult.organization_id == principal.organization_id,
        )
        .order_by(
            StructuredAnalysisResult.prompt_type.asc(),
            StructuredAnalysisResult.version.desc(),
        )
        .all()
    )
    return [_result_out(result) for result in results]


@router.post(
    "/analysis-runs/{run_id}/structured-results/import-legacy",
    response_model=list[StructuredResultOut],
)
def import_legacy_analysis_results(
    run_id: str,
    principal: CurrentPrincipal = Depends(require_roles(*CREATE_ROLES)),
    db: Session = Depends(get_db),
):
    run, contract = get_run_for_organization(db, principal.organization_id, run_id)
    results = import_legacy_results(
        db,
        organization_id=principal.organization_id,
        user_id=principal.user_id,
        run=run,
        contract=contract,
    )
    record_audit(
        db,
        "analysis.structured_imported",
        organization_id=principal.organization_id,
        user_id=principal.user_id,
        resource_type="analysis_run",
        resource_id=run.id,
        details={"contract_id": contract.id, "result_ids": [item.id for item in results]},
    )
    db.commit()
    return [_result_out(result) for result in results]


@router.post(
    "/analysis-runs/{run_id}/structured-results",
    response_model=StructuredResultOut,
    status_code=201,
)
def create_structured_result(
    run_id: str,
    data: StructuredResultCreate,
    principal: CurrentPrincipal = Depends(require_roles(*CREATE_ROLES)),
    db: Session = Depends(get_db),
):
    run, contract = get_run_for_organization(db, principal.organization_id, run_id)
    validate_run_links(db, principal.organization_id, run, contract)
    source = None
    if data.source_result_id:
        source = (
            db.query(AnalysisResult)
            .filter(
                AnalysisResult.id == data.source_result_id,
                AnalysisResult.analysis_run_id == run.id,
            )
            .one_or_none()
        )
        if source is None:
            raise HTTPException(status_code=422, detail="原始结果不属于当前分析运行")
    result = create_result_version(
        db,
        organization_id=principal.organization_id,
        user_id=principal.user_id,
        run=run,
        contract=contract,
        payload=data,
        prompt_type=data.prompt_type,
        source_result=source,
        raw_json=data.model_dump(mode="json"),
    )
    record_audit(
        db,
        "analysis.structured_created",
        organization_id=principal.organization_id,
        user_id=principal.user_id,
        resource_type="structured_analysis_result",
        resource_id=result.id,
        details={"run_id": run.id, "contract_id": contract.id, "version": result.version},
    )
    db.commit()
    return _result_out(result)


@router.post(
    "/analysis-runs/{run_id}/structured-results/{result_id}/revisions",
    response_model=StructuredResultOut,
    status_code=201,
)
def create_structured_revision(
    run_id: str,
    result_id: str,
    data: StructuredRevisionCreate,
    principal: CurrentPrincipal = Depends(require_roles(*CREATE_ROLES)),
    db: Session = Depends(get_db),
):
    run, contract, base = _get_result(db, principal, run_id, result_id)
    latest_version = max(
        item.version for item in run.structured_results if item.prompt_type == base.prompt_type
    )
    if base.version != latest_version:
        raise HTTPException(status_code=409, detail="只能从当前最新版本创建修订")
    if base.status not in {"draft", "rejected"}:
        raise HTTPException(status_code=409, detail="只能修订草稿或已驳回版本")
    result = create_result_version(
        db,
        organization_id=principal.organization_id,
        user_id=principal.user_id,
        run=run,
        contract=contract,
        payload=data,
        prompt_type=base.prompt_type,
        source_result=base.source_result,
        raw_json=data.model_dump(mode="json"),
    )
    base.status = "superseded"
    record_audit(
        db,
        "analysis.structured_revised",
        organization_id=principal.organization_id,
        user_id=principal.user_id,
        resource_type="structured_analysis_result",
        resource_id=result.id,
        details={"run_id": run.id, "base_result_id": base.id, "version": result.version},
    )
    db.commit()
    return _result_out(result)


@router.post(
    "/analysis-runs/{run_id}/structured-results/{result_id}/submit",
    response_model=StructuredResultOut,
)
def submit_structured_result(
    run_id: str,
    result_id: str,
    principal: CurrentPrincipal = Depends(require_roles(*CREATE_ROLES)),
    db: Session = Depends(get_db),
):
    run, contract, result = _get_result(db, principal, run_id, result_id)
    submit_for_review(result)
    record_audit(
        db,
        "analysis.review_submitted",
        organization_id=principal.organization_id,
        user_id=principal.user_id,
        resource_type="structured_analysis_result",
        resource_id=result.id,
        details={"run_id": run.id, "contract_id": contract.id, "version": result.version},
    )
    db.commit()
    db.refresh(result)
    return _result_out(result)


@router.post(
    "/analysis-runs/{run_id}/structured-results/{result_id}/review",
    response_model=StructuredResultOut,
)
def review_structured_result(
    run_id: str,
    result_id: str,
    data: ReviewDecision,
    principal: CurrentPrincipal = Depends(require_roles(*REVIEW_ROLES)),
    db: Session = Depends(get_db),
):
    run, contract, result = _get_result(db, principal, run_id, result_id)
    review_result(
        result,
        decision=data.decision,
        comment=data.comment,
        reviewer_id=principal.user_id,
    )
    record_audit(
        db,
        f"analysis.review_{data.decision}",
        organization_id=principal.organization_id,
        user_id=principal.user_id,
        resource_type="structured_analysis_result",
        resource_id=result.id,
        details={"run_id": run.id, "contract_id": contract.id, "version": result.version},
    )
    db.commit()
    db.refresh(result)
    return _result_out(result)


@router.patch(
    "/analysis-runs/{run_id}/structured-results/{result_id}/risks/{risk_id}",
    response_model=StructuredResultOut,
)
def update_analysis_risk(
    run_id: str,
    result_id: str,
    risk_id: str,
    data: RiskStatusUpdate,
    principal: CurrentPrincipal = Depends(require_roles(*REVIEW_ROLES)),
    db: Session = Depends(get_db),
):
    run, contract, result = _get_result(db, principal, run_id, result_id)
    if result.status != "in_review":
        raise HTTPException(status_code=409, detail="只有待复核结果的风险项可以处置")
    risk = (
        db.query(AnalysisRisk)
        .filter(
            AnalysisRisk.id == risk_id,
            AnalysisRisk.structured_result_id == result.id,
            AnalysisRisk.organization_id == principal.organization_id,
            AnalysisRisk.contract_id == contract.id,
        )
        .one_or_none()
    )
    if risk is None:
        raise HTTPException(status_code=404, detail="风险项不存在")
    update_risk(
        risk,
        user_id=principal.user_id,
        roles=principal.roles,
        status=data.status,
        comment=data.comment,
    )
    record_audit(
        db,
        "analysis.risk_reviewed",
        organization_id=principal.organization_id,
        user_id=principal.user_id,
        resource_type="analysis_risk",
        resource_id=risk.id,
        details={
            "run_id": run.id,
            "contract_id": contract.id,
            "result_id": result.id,
            "status": data.status,
        },
    )
    db.commit()
    db.refresh(result)
    return _result_out(result)
