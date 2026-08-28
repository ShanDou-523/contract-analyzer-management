"""Add durable jobs, notification delivery state, and daily risk snapshots."""

from sqlalchemy import (
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
)

from alembic import op

revision = "0010_background_jobs_snapshots"
down_revision = "0009_risk_notifications_reports"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    metadata = MetaData()
    Table("organizations", metadata, Column("id", String(36), primary_key=True))
    Table("users", metadata, Column("id", String(36), primary_key=True))
    Table("notifications", metadata, Column("id", String(36), primary_key=True))
    background_jobs = Table(
        "background_jobs",
        metadata,
        Column("id", String(36), primary_key=True),
        Column("organization_id", String(36), ForeignKey("organizations.id"), nullable=False),
        Column("job_type", String(50), nullable=False),
        Column("status", String(20), nullable=False),
        Column("priority", Integer, nullable=False),
        Column("payload_json", Text, nullable=False),
        Column("result_json", Text, nullable=False),
        Column("dedupe_key", String(160), nullable=False),
        Column("attempts", Integer, nullable=False),
        Column("max_attempts", Integer, nullable=False),
        Column("available_at", DateTime(timezone=True), nullable=False),
        Column("locked_at", DateTime(timezone=True)),
        Column("locked_by", String(100)),
        Column("started_at", DateTime(timezone=True)),
        Column("finished_at", DateTime(timezone=True)),
        Column("requested_by", String(36), ForeignKey("users.id")),
        Column("error_code", String(100)),
        Column("error_message", Text),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("updated_at", DateTime(timezone=True), nullable=False),
        UniqueConstraint("dedupe_key", name="uq_background_jobs_dedupe_key"),
        Index("ix_background_jobs_organization_id", "organization_id"),
        Index("ix_background_jobs_job_type", "job_type"),
        Index("ix_background_jobs_status", "status"),
        Index("ix_background_jobs_available_at", "available_at"),
        Index("ix_background_jobs_locked_at", "locked_at"),
        Index("ix_background_jobs_requested_by", "requested_by"),
        Index("ix_background_jobs_claim", "status", "available_at", "priority"),
        Index("ix_background_jobs_org_created", "organization_id", "created_at"),
    )
    notification_deliveries = Table(
        "notification_deliveries",
        metadata,
        Column("id", String(36), primary_key=True),
        Column("organization_id", String(36), ForeignKey("organizations.id"), nullable=False),
        Column("notification_id", String(36), ForeignKey("notifications.id"), nullable=False),
        Column("background_job_id", String(36), ForeignKey("background_jobs.id")),
        Column("provider_name", String(50), nullable=False),
        Column("channel", String(30), nullable=False),
        Column("status", String(20), nullable=False),
        Column("attempt_count", Integer, nullable=False),
        Column("max_attempts", Integer, nullable=False),
        Column("last_error", Text),
        Column("provider_message_id", String(200)),
        Column("next_retry_at", DateTime(timezone=True)),
        Column("sent_at", DateTime(timezone=True)),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("updated_at", DateTime(timezone=True), nullable=False),
        UniqueConstraint(
            "notification_id", "provider_name", name="uq_notification_delivery_provider"
        ),
        Index("ix_notification_deliveries_organization_id", "organization_id"),
        Index("ix_notification_deliveries_notification_id", "notification_id"),
        Index("ix_notification_deliveries_background_job_id", "background_job_id"),
        Index("ix_notification_deliveries_provider_name", "provider_name"),
        Index("ix_notification_deliveries_status", "status"),
        Index(
            "ix_notification_deliveries_org_status", "organization_id", "status", "updated_at"
        ),
    )
    risk_snapshots = Table(
        "risk_report_snapshots",
        metadata,
        Column("id", String(36), primary_key=True),
        Column("organization_id", String(36), ForeignKey("organizations.id"), nullable=False),
        Column("snapshot_date", Date, nullable=False),
        Column("total", Integer, nullable=False),
        Column("active", Integer, nullable=False),
        Column("overdue", Integer, nullable=False),
        Column("closed", Integer, nullable=False),
        Column("critical", Integer, nullable=False),
        Column("overdue_rate", Numeric(8, 4), nullable=False),
        Column("contract_rankings_json", Text, nullable=False),
        Column("assignee_workloads_json", Text, nullable=False),
        Column("source_job_id", String(36), ForeignKey("background_jobs.id")),
        Column("generated_at", DateTime(timezone=True), nullable=False),
        UniqueConstraint("organization_id", "snapshot_date", name="uq_risk_snapshot_org_date"),
        Index("ix_risk_report_snapshots_organization_id", "organization_id"),
        Index("ix_risk_report_snapshots_snapshot_date", "snapshot_date"),
        Index("ix_risk_report_snapshots_source_job_id", "source_job_id"),
        Index("ix_risk_snapshots_org_date", "organization_id", "snapshot_date"),
    )
    metadata.create_all(bind=bind, tables=[background_jobs, notification_deliveries, risk_snapshots])


def downgrade() -> None:
    # Job, delivery, and report history is intentionally retained.
    pass
