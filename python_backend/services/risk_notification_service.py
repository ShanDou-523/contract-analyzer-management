"""Idempotent risk remediation reminder generation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from core.security import as_utc
from models.contract import AnalysisRisk, Contract, Notification, StructuredAnalysisResult, User
from services.risk_service import ACTIVE_REMEDIATION_STATUSES

REMINDER_WINDOW = timedelta(days=1)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class RiskReminderScanResult:
    examined_risks: int
    created: int
    skipped_existing: int
    skipped_without_recipient: int


def _dedupe_key(risk_id: str, recipient_id: str, notification_type: str, source_at: datetime) -> str:
    value = f"risk|{risk_id}|{recipient_id}|{notification_type}|{as_utc(source_at).isoformat()}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def scan_risk_reminders(
    db: Session,
    organization_id: str,
    *,
    now: datetime | None = None,
) -> RiskReminderScanResult:
    """Generate due/overdue risk notifications without calling external services."""
    scan_at = as_utc(now or now_utc())
    rows = (
        db.query(AnalysisRisk, Contract, StructuredAnalysisResult)
        .join(Contract, Contract.id == AnalysisRisk.contract_id)
        .join(StructuredAnalysisResult, StructuredAnalysisResult.id == AnalysisRisk.structured_result_id)
        .filter(
            AnalysisRisk.organization_id == organization_id,
            AnalysisRisk.status.in_(ACTIVE_REMEDIATION_STATUSES),
            AnalysisRisk.remediation_due_at.isnot(None),
            Contract.organization_id == organization_id,
            Contract.deleted_at.is_(None),
            StructuredAnalysisResult.organization_id == organization_id,
            StructuredAnalysisResult.status != "superseded",
        )
        .all()
    )
    user_ids = {
        user_id
        for risk, _contract, _result in rows
        for user_id in (risk.assignee_id, risk.created_by)
        if user_id
    }
    users = {
        user.id: user
        for user in db.query(User)
        .filter(
            User.id.in_(user_ids),
            User.organization_id == organization_id,
            User.status == "active",
        )
        .all()
    }

    candidates: list[tuple[AnalysisRisk, Contract, User, str, datetime]] = []
    skipped_without_recipient = 0
    for risk, contract, _result in rows:
        recipient = users.get(risk.assignee_id) if risk.assignee_id else None
        recipient = recipient or users.get(risk.created_by)
        if recipient is None:
            skipped_without_recipient += 1
            continue
        due_at = as_utc(risk.remediation_due_at)
        if due_at is None:
            continue
        if due_at < scan_at:
            candidates.append((risk, contract, recipient, "risk_overdue", due_at))
        elif due_at <= scan_at + REMINDER_WINDOW:
            candidates.append((risk, contract, recipient, "risk_reminder", due_at))

    keyed_candidates = [
        (*candidate, _dedupe_key(candidate[0].id, candidate[2].id, candidate[3], candidate[4]))
        for candidate in candidates
    ]
    candidate_keys = [candidate[5] for candidate in keyed_candidates]
    existing_keys = set()
    if candidate_keys:
        existing_keys = {
            key
            for (key,) in db.query(Notification.dedupe_key)
            .filter(
                Notification.organization_id == organization_id,
                Notification.dedupe_key.in_(candidate_keys),
            )
            .all()
        }

    created = 0
    for risk, contract, recipient, notification_type, source_at, dedupe_key in keyed_candidates:
        if dedupe_key in existing_keys:
            continue
        overdue = notification_type == "risk_overdue"
        db.add(
            Notification(
                organization_id=organization_id,
                recipient_id=recipient.id,
                contract_id=contract.id,
                task_id=None,
                risk_id=risk.id,
                notification_type=notification_type,
                status="unread",
                title=f"{'风险整改已逾期' if overdue else '风险整改提醒'}：{risk.title}",
                message=(
                    f"合同“{contract.name}”的风险项“{risk.title}”"
                    f"{'已超过整改期限' if overdue else '将在 24 小时内到期'}。"
                ),
                source_at=source_at,
                dedupe_key=dedupe_key,
                metadata_json=json.dumps(
                    {
                        "contract_no": contract.contract_no,
                        "risk_code": risk.code,
                        "severity": risk.severity,
                        "remediation_due_at": as_utc(source_at).isoformat(),
                    },
                    ensure_ascii=False,
                ),
                generated_at=scan_at,
            )
        )
        existing_keys.add(dedupe_key)
        created += 1
    db.flush()
    return RiskReminderScanResult(
        examined_risks=len(rows),
        created=created,
        skipped_existing=len(keyed_candidates) - created,
        skipped_without_recipient=skipped_without_recipient,
    )
