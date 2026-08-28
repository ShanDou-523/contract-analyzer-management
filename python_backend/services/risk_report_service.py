"""Read-only organization-scoped aggregations for risk management reports."""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from models.contract import AnalysisRisk, Contract, StructuredAnalysisResult, User
from schemas.risk_reports import (
    RiskAssigneeWorkload,
    RiskContractRanking,
    RiskReportOverview,
    RiskTrendPoint,
)
from services.risk_service import is_overdue, summarize_risks


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def report_rows(db: Session, organization_id: str):
    return (
        db.query(AnalysisRisk, Contract, StructuredAnalysisResult, User)
        .join(Contract, Contract.id == AnalysisRisk.contract_id)
        .join(StructuredAnalysisResult, StructuredAnalysisResult.id == AnalysisRisk.structured_result_id)
        .outerjoin(User, (User.id == AnalysisRisk.assignee_id) & (User.organization_id == organization_id))
        .filter(
            AnalysisRisk.organization_id == organization_id,
            Contract.organization_id == organization_id,
            Contract.deleted_at.is_(None),
            StructuredAnalysisResult.organization_id == organization_id,
            StructuredAnalysisResult.status != "superseded",
        )
        .all()
    )


def _created_date(value: datetime | None) -> date:
    if value is None:
        return date.today()
    normalized = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    return normalized.date()


def build_overview(
    db: Session,
    organization_id: str,
    *,
    period_days: int = 30,
    now: datetime | None = None,
) -> RiskReportOverview:
    generated_at = now or now_utc()
    generated_at = generated_at.replace(tzinfo=timezone.utc) if generated_at.tzinfo is None else generated_at.astimezone(timezone.utc)
    rows = report_rows(db, organization_id)
    risks = [risk for risk, _contract, _result, _assignee in rows]

    trend_buckets: dict[date, dict[str, int]] = defaultdict(lambda: {"total": 0, "open": 0, "overdue": 0, "closed": 0})
    start_date = generated_at.date() - timedelta(days=period_days - 1)
    for day_offset in range(period_days):
        trend_buckets[start_date + timedelta(days=day_offset)]
    for risk in risks:
        created_day = _created_date(risk.created_at)
        if created_day not in trend_buckets:
            continue
        bucket = trend_buckets[created_day]
        bucket["total"] += 1
        if risk.status in {"open", "in_progress"}:
            bucket["open"] += 1
        if is_overdue(risk, generated_at):
            bucket["overdue"] += 1
        if risk.status == "closed":
            bucket["closed"] += 1

    contract_groups: dict[str, dict[str, object]] = {}
    assignee_groups: dict[str | None, dict[str, object]] = {}
    for risk, contract, _result, assignee in rows:
        contract_group = contract_groups.setdefault(
            contract.id,
            {"contract_id": contract.id, "contract_name": contract.name, "contract_no": contract.contract_no, "total": 0, "open": 0, "critical": 0, "overdue": 0},
        )
        contract_group["total"] += 1
        contract_group["open"] += int(risk.status in {"open", "in_progress"})
        contract_group["critical"] += int(risk.severity == "critical")
        contract_group["overdue"] += int(is_overdue(risk, generated_at))

        assignee_id = risk.assignee_id
        assignee_group = assignee_groups.setdefault(
            assignee_id,
            {
                "assignee_id": assignee_id,
                "assignee_name": (assignee.display_name or assignee.username) if assignee else "未分配",
                "total": 0,
                "open": 0,
                "overdue": 0,
                "closed": 0,
            },
        )
        assignee_group["total"] += 1
        assignee_group["open"] += int(risk.status in {"open", "in_progress"})
        assignee_group["overdue"] += int(is_overdue(risk, generated_at))
        assignee_group["closed"] += int(risk.status == "closed")

    contract_rankings = [RiskContractRanking(**item) for item in contract_groups.values()]
    contract_rankings.sort(key=lambda item: (-item.overdue, -item.critical, -item.open, item.contract_name))
    assignee_workloads = [RiskAssigneeWorkload(**item) for item in assignee_groups.values()]
    assignee_workloads.sort(key=lambda item: (-item.overdue, -item.open, item.assignee_name))
    trend = [RiskTrendPoint(date=day.isoformat(), **trend_buckets[day]) for day in sorted(trend_buckets)]
    return RiskReportOverview(
        generated_at=generated_at,
        period_days=period_days,
        summary=summarize_risks(db, organization_id),
        trend=trend,
        contract_rankings=contract_rankings,
        assignee_workloads=assignee_workloads,
    )


def export_csv(overview: RiskReportOverview) -> str:
    """Return a UTF-8 CSV with one row per contract ranking."""
    output = io.StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(["合同风险报表"])
    writer.writerow(["生成时间", overview.generated_at.isoformat()])
    writer.writerow(["统计周期（天）", overview.period_days])
    writer.writerow([])
    writer.writerow(["合同编号", "合同名称", "风险总数", "待处置", "严重风险", "逾期"])
    for item in overview.contract_rankings:
        writer.writerow(
            [item.contract_no or "", item.contract_name, item.total, item.open, item.critical, item.overdue]
        )
    writer.writerow([])
    writer.writerow(["负责人", "风险总数", "待处置", "逾期", "已关闭"])
    for item in overview.assignee_workloads:
        writer.writerow([item.assignee_name, item.total, item.open, item.overdue, item.closed])
    return "\ufeff" + output.getvalue()
