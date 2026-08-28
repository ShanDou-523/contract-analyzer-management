"""Structured analysis versioning and deterministic legacy-result conversion."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from models.contract import (
    AnalysisEvidence,
    AnalysisRisk,
    AnalysisRun,
    AnalysisTemplateVersion,
    Contract,
    ContractFile,
    FileVersion,
    StructuredAnalysisField,
    StructuredAnalysisResult,
)
from models.document import AnalysisResult, AnalysisTemplate
from schemas.structured_analysis import (
    EvidenceInput,
    RiskInput,
    StructuredFieldInput,
    StructuredResultCreate,
    StructuredRevisionCreate,
)

EDITABLE_STATUSES = {"draft", "rejected"}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def parse_json_object(text: str | None) -> dict[str, Any]:
    if not text:
        raise HTTPException(status_code=422, detail="原始分析结果为空")
    candidate = text.strip()
    if candidate.startswith("```"):
        lines = candidate.splitlines()
        candidate = "\n".join(lines[1:-1]) if len(lines) >= 3 else candidate
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail="原始分析结果不是合法 JSON") from exc
    if not isinstance(value, dict):
        raise HTTPException(status_code=422, detail="原始分析结果必须是 JSON 对象")
    return value


def get_run_for_organization(
    db: Session,
    organization_id: str,
    run_id: str,
) -> tuple[AnalysisRun, Contract]:
    row = (
        db.query(AnalysisRun, Contract)
        .join(Contract, Contract.id == AnalysisRun.contract_id)
        .filter(
            AnalysisRun.id == run_id,
            Contract.organization_id == organization_id,
            Contract.deleted_at.is_(None),
        )
        .one_or_none()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="分析运行不存在")
    return row


def validate_run_links(
    db: Session,
    organization_id: str,
    run: AnalysisRun,
    contract: Contract,
) -> tuple[FileVersion, AnalysisTemplateVersion]:
    if not run.file_version_id or not run.template_version_id:
        raise HTTPException(status_code=422, detail="分析运行缺少文件版本或模板版本关联")
    file_version = (
        db.query(FileVersion)
        .join(ContractFile, ContractFile.id == FileVersion.contract_file_id)
        .filter(
            FileVersion.id == run.file_version_id,
            ContractFile.contract_id == contract.id,
            FileVersion.deleted_at.is_(None),
        )
        .one_or_none()
    )
    template_version = (
        db.query(AnalysisTemplateVersion)
        .join(AnalysisTemplate, AnalysisTemplate.id == AnalysisTemplateVersion.template_id)
        .filter(
            AnalysisTemplateVersion.id == run.template_version_id,
            AnalysisTemplate.organization_id == organization_id,
        )
        .one_or_none()
    )
    if file_version is None or template_version is None:
        raise HTTPException(status_code=422, detail="分析运行的文件版本或模板版本不属于当前合同组织")
    return file_version, template_version


def _value_parts(value: Any) -> tuple[str, str]:
    encoded = json.dumps(value, ensure_ascii=False)
    if value is None:
        return "", encoded
    if isinstance(value, str):
        return value, encoded
    return json.dumps(value, ensure_ascii=False), encoded


def _next_version(db: Session, run_id: str, prompt_type: str) -> int:
    current = (
        db.query(func.max(StructuredAnalysisResult.version))
        .filter(
            StructuredAnalysisResult.analysis_run_id == run_id,
            StructuredAnalysisResult.prompt_type == prompt_type,
        )
        .scalar()
    )
    return int(current or 0) + 1


def create_result_version(
    db: Session,
    *,
    organization_id: str,
    user_id: str,
    run: AnalysisRun,
    contract: Contract,
    payload: StructuredResultCreate | StructuredRevisionCreate,
    prompt_type: str,
    source_result: AnalysisResult | None = None,
    raw_json: dict[str, Any] | None = None,
) -> StructuredAnalysisResult:
    validate_run_links(db, organization_id, run, contract)
    version = _next_version(db, run.id, prompt_type)
    result = StructuredAnalysisResult(
        organization_id=organization_id,
        contract_id=contract.id,
        analysis_run_id=run.id,
        source_result_id=source_result.id if source_result else None,
        file_version_id=run.file_version_id,
        template_version_id=run.template_version_id,
        prompt_type=prompt_type,
        version=version,
        status="draft",
        summary=payload.summary,
        raw_json=json.dumps(raw_json or {}, ensure_ascii=False),
        created_by=user_id,
    )
    db.add(result)
    db.flush()

    for position, field in enumerate(payload.fields):
        value_text, value_json = _value_parts(field.value)
        db.add(
            StructuredAnalysisField(
                structured_result_id=result.id,
                field_key=field.field_key,
                label=field.label,
                value_text=value_text,
                value_json=value_json,
                confidence=field.confidence,
                position=position,
            )
        )

    evidence_rows: list[AnalysisEvidence] = []
    for evidence in payload.evidence:
        row = AnalysisEvidence(
            organization_id=organization_id,
            contract_id=contract.id,
            structured_result_id=result.id,
            file_version_id=run.file_version_id,
            page_no=evidence.page_no,
            char_start=evidence.char_start,
            char_end=evidence.char_end,
            quote=evidence.quote,
            locator_json=json.dumps(evidence.locator, ensure_ascii=False),
            created_by=user_id,
        )
        db.add(row)
        db.flush()
        evidence_rows.append(row)

    for risk in payload.risks:
        if risk.evidence_index is not None and risk.evidence_index >= len(evidence_rows):
            raise HTTPException(status_code=422, detail="风险项引用的证据序号不存在")
        evidence_id = (
            evidence_rows[risk.evidence_index].id if risk.evidence_index is not None else None
        )
        db.add(
            AnalysisRisk(
                organization_id=organization_id,
                contract_id=contract.id,
                structured_result_id=result.id,
                evidence_id=evidence_id,
                code=risk.code,
                title=risk.title,
                description=risk.description,
                severity=risk.severity,
                status=risk.status,
                reviewer_comment=risk.reviewer_comment,
                created_by=user_id,
            )
        )
    db.flush()
    db.refresh(result)
    return result


def _legacy_fields(source: AnalysisResult, parsed: dict[str, Any]) -> list[StructuredFieldInput]:
    snapshots: list[dict[str, Any]] = []
    if source.fields_snapshot_json:
        try:
            value = json.loads(source.fields_snapshot_json)
            snapshots = value if isinstance(value, list) else []
        except json.JSONDecodeError:
            snapshots = []
    label_map = {
        str(item.get("key")): str(item.get("label") or item.get("key"))
        for item in snapshots
        if isinstance(item, dict) and item.get("key")
    }
    return [
        StructuredFieldInput(
            field_key=str(key),
            label=label_map.get(str(key), str(key)),
            value=value,
        )
        for key, value in parsed.items()
    ]


def _severity(value: Any) -> str:
    return {"严重": "critical", "警告": "high", "注意": "medium"}.get(
        str(value), "low"
    )


def _legacy_review_payload(parsed: dict[str, Any]) -> StructuredResultCreate:
    evidence: list[EvidenceInput] = []
    risks: list[RiskInput] = []
    issues = parsed.get("数据问题", [])
    if isinstance(issues, list):
        for index, item in enumerate(issues):
            if not isinstance(item, dict) or item.get("是否有问题") != "是":
                continue
            quote = str(item.get("合同标注") or "").strip()
            evidence_index = None
            if quote and quote not in {"未提及", "无", "-"}:
                evidence_index = len(evidence)
                evidence.append(EvidenceInput(quote=quote, locator={"source": "legacy_review"}))
            risks.append(
                RiskInput(
                    code=f"legacy-risk-{index + 1}",
                    title=str(item.get("项目") or f"风险项 {index + 1}"),
                    description=str(item.get("说明") or item.get("描述/公式") or ""),
                    severity=_severity(item.get("严重程度")),
                    evidence_index=evidence_index,
                )
            )
    fields: list[StructuredFieldInput] = []
    reasonability = parsed.get("内容合理性", [])
    if isinstance(reasonability, list):
        for index, item in enumerate(reasonability):
            if not isinstance(item, dict):
                continue
            fields.append(
                StructuredFieldInput(
                    field_key=f"reasonability_{index + 1}",
                    label=str(item.get("方面") or f"合理性 {index + 1}"),
                    value={"评价": item.get("评价"), "建议": item.get("建议")},
                )
            )
    return StructuredResultCreate(
        prompt_type="reasonability_check",
        summary=str(parsed.get("总结") or ""),
        fields=fields,
        evidence=evidence,
        risks=risks,
    )


def import_legacy_results(
    db: Session,
    *,
    organization_id: str,
    user_id: str,
    run: AnalysisRun,
    contract: Contract,
) -> list[StructuredAnalysisResult]:
    validate_run_links(db, organization_id, run, contract)
    sources = (
        db.query(AnalysisResult)
        .filter(AnalysisResult.analysis_run_id == run.id)
        .order_by(AnalysisResult.created_at.desc(), AnalysisResult.id.desc())
        .all()
    )
    latest: dict[str, AnalysisResult] = {}
    for source in sources:
        latest.setdefault(source.prompt_type, source)
    if not latest:
        raise HTTPException(status_code=422, detail="分析运行没有可转换的原始结果")

    imported: list[StructuredAnalysisResult] = []
    for prompt_type, source in latest.items():
        existing = (
            db.query(StructuredAnalysisResult)
            .filter(
                StructuredAnalysisResult.source_result_id == source.id,
                StructuredAnalysisResult.analysis_run_id == run.id,
                StructuredAnalysisResult.organization_id == organization_id,
            )
            .order_by(StructuredAnalysisResult.version.desc())
            .first()
        )
        if existing:
            imported.append(existing)
            continue
        parsed = parse_json_object(source.response_text)
        if prompt_type == "reasonability_check":
            payload = _legacy_review_payload(parsed)
        else:
            payload = StructuredResultCreate(
                prompt_type=prompt_type,
                fields=_legacy_fields(source, parsed),
            )
        imported.append(
            create_result_version(
                db,
                organization_id=organization_id,
                user_id=user_id,
                run=run,
                contract=contract,
                payload=payload,
                prompt_type=prompt_type,
                source_result=source,
                raw_json=parsed,
            )
        )
    return imported


def submit_for_review(result: StructuredAnalysisResult) -> None:
    if result.status not in EDITABLE_STATUSES:
        raise HTTPException(status_code=409, detail="只有草稿或已驳回版本可以提交复核")
    result.status = "in_review"
    result.reviewed_by = None
    result.reviewed_at = None
    result.review_comment = None


def review_result(
    result: StructuredAnalysisResult,
    *,
    decision: str,
    comment: str,
    reviewer_id: str,
) -> None:
    if result.status != "in_review":
        raise HTTPException(status_code=409, detail="只有待复核版本可以审批")
    if decision == "approved" and any(risk.status == "open" for risk in result.risks):
        raise HTTPException(status_code=409, detail="仍有未处置风险项，不能批准")
    result.status = decision
    result.review_comment = comment.strip() or None
    result.reviewed_by = reviewer_id
    result.reviewed_at = now_utc()
