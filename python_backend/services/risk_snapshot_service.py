"""Daily organization-scoped risk report snapshots and CSV export."""

from __future__ import annotations

import csv
import io
import json
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from models.contract import RiskReportSnapshot
from schemas.risk_reports import (
    RiskAssigneeWorkload,
    RiskContractRanking,
    RiskReportSnapshotOut,
)
from services.risk_report_service import build_overview


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _decode_list(value: str | None) -> list[dict]:
    try:
        decoded = json.loads(value or "[]")
    except (TypeError, ValueError):
        return []
    return decoded if isinstance(decoded, list) else []


def create_daily_snapshot(
    db: Session,
    organization_id: str,
    *,
    snapshot_date: date | None = None,
    generated_at: datetime | None = None,
    source_job_id: str | None = None,
) -> RiskReportSnapshot:
    current = generated_at or now_utc()
    current = current.replace(tzinfo=timezone.utc) if current.tzinfo is None else current.astimezone(timezone.utc)
    target_date = snapshot_date or current.date()
    overview = build_overview(db, organization_id, period_days=30, now=current)
    active = overview.summary.open + overview.summary.in_progress
    critical = next(
        (item.count for item in overview.summary.by_severity if item.key == "critical"), 0
    )
    overdue_rate = Decimal(str(round((overview.summary.overdue / active * 100) if active else 0, 4)))
    snapshot = (
        db.query(RiskReportSnapshot)
        .filter(
            RiskReportSnapshot.organization_id == organization_id,
            RiskReportSnapshot.snapshot_date == target_date,
        )
        .one_or_none()
    )
    if snapshot is None:
        snapshot = RiskReportSnapshot(
            organization_id=organization_id,
            snapshot_date=target_date,
        )
        db.add(snapshot)
    snapshot.total = overview.summary.total
    snapshot.active = active
    snapshot.overdue = overview.summary.overdue
    snapshot.closed = overview.summary.closed
    snapshot.critical = critical
    snapshot.overdue_rate = overdue_rate
    snapshot.contract_rankings_json = json.dumps(
        [item.model_dump(mode="json") for item in overview.contract_rankings], ensure_ascii=False
    )
    snapshot.assignee_workloads_json = json.dumps(
        [item.model_dump(mode="json") for item in overview.assignee_workloads], ensure_ascii=False
    )
    snapshot.source_job_id = source_job_id
    snapshot.generated_at = current
    db.flush()
    return snapshot


def snapshot_out(snapshot: RiskReportSnapshot) -> RiskReportSnapshotOut:
    return RiskReportSnapshotOut(
        id=snapshot.id,
        organization_id=snapshot.organization_id,
        snapshot_date=snapshot.snapshot_date.isoformat(),
        total=snapshot.total,
        active=snapshot.active,
        overdue=snapshot.overdue,
        closed=snapshot.closed,
        critical=snapshot.critical,
        overdue_rate=float(snapshot.overdue_rate or 0),
        contract_rankings=[
            RiskContractRanking.model_validate(item)
            for item in _decode_list(snapshot.contract_rankings_json)
        ],
        assignee_workloads=[
            RiskAssigneeWorkload.model_validate(item)
            for item in _decode_list(snapshot.assignee_workloads_json)
        ],
        source_job_id=snapshot.source_job_id,
        generated_at=snapshot.generated_at,
    )


def export_snapshots_csv(snapshots: list[RiskReportSnapshot]) -> str:
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["日期", "风险总数", "待处置", "逾期", "逾期率", "严重风险", "已关闭"])
    for snapshot in snapshots:
        writer.writerow(
            [
                snapshot.snapshot_date.isoformat(),
                snapshot.total,
                snapshot.active,
                snapshot.overdue,
                f"{float(snapshot.overdue_rate or 0):.2f}%",
                snapshot.critical,
                snapshot.closed,
            ]
        )
    return "\ufeff" + output.getvalue()
