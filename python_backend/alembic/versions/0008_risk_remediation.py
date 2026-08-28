"""Add risk remediation ownership, deadlines, and closure metadata."""

from sqlalchemy import Column, DateTime, ForeignKey, String, Text, inspect

from alembic import op

revision = "0008_risk_remediation"
down_revision = "0007_structured_analysis_review"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {item["name"] for item in inspect(bind).get_columns("analysis_risks")}
    definitions = (
        (
            "assignee_id",
            Column(
                "assignee_id",
                String(36),
                ForeignKey("users.id", name="fk_analysis_risks_assignee_id_users"),
                nullable=True,
            ),
        ),
        ("remediation_due_at", Column("remediation_due_at", DateTime(timezone=True), nullable=True)),
        ("remediation_notes", Column("remediation_notes", Text, nullable=True)),
        (
            "closed_by",
            Column(
                "closed_by",
                String(36),
                ForeignKey("users.id", name="fk_analysis_risks_closed_by_users"),
                nullable=True,
            ),
        ),
        ("closed_at", Column("closed_at", DateTime(timezone=True), nullable=True)),
        ("closure_comment", Column("closure_comment", Text, nullable=True)),
    )
    missing = [column for name, column in definitions if name not in columns]
    if missing:
        with op.batch_alter_table("analysis_risks", recreate="always") as batch_op:
            for column in missing:
                batch_op.add_column(column)

    existing = {item["name"] for item in inspect(bind).get_indexes("analysis_risks")}
    for name, columns_for_index in (
        ("ix_analysis_risks_assignee_id", ["assignee_id"]),
        ("ix_analysis_risks_remediation_due_at", ["remediation_due_at"]),
        ("ix_analysis_risks_org_status_due", ["organization_id", "status", "remediation_due_at"]),
    ):
        if name not in existing:
            op.create_index(name, "analysis_risks", columns_for_index, unique=False)


def downgrade() -> None:
    # Risk remediation history must remain recoverable; restore a pre-stage8 backup instead.
    pass
