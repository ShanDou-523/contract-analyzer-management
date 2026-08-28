"""Allow idempotent risk reminder notifications."""

from sqlalchemy import Column, ForeignKey, String, inspect

from alembic import op

revision = "0009_risk_notifications_reports"
down_revision = "0008_risk_remediation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {item["name"] for item in inspect(bind).get_columns("notifications")}
    with op.batch_alter_table("notifications", recreate="always") as batch_op:
        if "task_id" in columns:
            batch_op.alter_column("task_id", existing_type=String(36), nullable=True)
        if "risk_id" not in columns:
            batch_op.add_column(
                Column(
                    "risk_id",
                    String(36),
                    ForeignKey("analysis_risks.id", name="fk_notifications_risk_id_analysis_risks"),
                    nullable=True,
                )
            )

    indexes = {item["name"] for item in inspect(bind).get_indexes("notifications")}
    if "ix_notifications_org_risk" not in indexes:
        op.create_index(
            "ix_notifications_org_risk", "notifications", ["organization_id", "risk_id"], unique=False
        )
    if "ix_notifications_risk_id" not in indexes:
        op.create_index("ix_notifications_risk_id", "notifications", ["risk_id"], unique=False)


def downgrade() -> None:
    # Notification and remediation history is intentionally retained.
    pass
