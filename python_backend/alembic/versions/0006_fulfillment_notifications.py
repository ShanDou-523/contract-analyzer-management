"""Add idempotent in-app notifications for fulfillment reminders."""

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    inspect,
)

from alembic import op

revision = "0006_fulfillment_notifications"
down_revision = "0005_parties_and_fulfillment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    metadata = MetaData()
    Table("organizations", metadata, Column("id", String(36), primary_key=True))
    Table("users", metadata, Column("id", String(36), primary_key=True))
    Table("contracts", metadata, Column("id", String(36), primary_key=True))
    Table("fulfillment_tasks", metadata, Column("id", String(36), primary_key=True))
    Table(
        "notifications",
        metadata,
        Column("id", String(36), primary_key=True),
        Column(
            "organization_id",
            String(36),
            ForeignKey("organizations.id"),
            nullable=False,
        ),
        Column("recipient_id", String(36), ForeignKey("users.id"), nullable=False),
        Column("contract_id", String(36), ForeignKey("contracts.id"), nullable=False),
        Column(
            "task_id",
            String(36),
            ForeignKey("fulfillment_tasks.id"),
            nullable=False,
        ),
        Column("notification_type", String(20), nullable=False),
        Column("status", String(20), nullable=False),
        Column("title", String(300), nullable=False),
        Column("message", Text, nullable=False),
        Column("source_at", DateTime(timezone=True), nullable=False),
        Column("dedupe_key", String(64), nullable=False),
        Column("metadata_json", Text, nullable=False),
        Column("generated_at", DateTime(timezone=True), nullable=False),
        Column("read_at", DateTime(timezone=True)),
        Column("ignored_at", DateTime(timezone=True)),
        UniqueConstraint("dedupe_key", name="uq_notifications_dedupe_key"),
    )
    metadata.create_all(bind=bind, checkfirst=True)

    indexes = {item["name"] for item in inspect(bind).get_indexes("notifications")}
    for column in (
        "organization_id",
        "recipient_id",
        "contract_id",
        "task_id",
        "notification_type",
        "status",
    ):
        name = f"ix_notifications_{column}"
        if name not in indexes:
            op.create_index(name, "notifications", [column], unique=False)
    for name, columns in (
        (
            "ix_notifications_org_recipient_status",
            ["organization_id", "recipient_id", "status"],
        ),
        ("ix_notifications_org_task", ["organization_id", "task_id"]),
    ):
        if name not in {item["name"] for item in inspect(bind).get_indexes("notifications")}:
            op.create_index(name, "notifications", columns, unique=False)


def downgrade() -> None:
    # Restore a pre-stage6 backup instead of dropping notification history.
    pass
