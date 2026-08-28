"""Add versioned structured analysis, evidence, and risk review tables."""

from sqlalchemy import (
    Column,
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
    inspect,
)

from alembic import op

revision = "0007_structured_analysis_review"
down_revision = "0006_fulfillment_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    metadata = MetaData()
    for table_name in (
        "organizations",
        "contracts",
        "analysis_runs",
        "analysis_results",
        "file_versions",
        "analysis_template_versions",
        "users",
    ):
        Table(table_name, metadata, Column("id", String(36), primary_key=True))

    Table(
        "structured_analysis_results",
        metadata,
        Column("id", String(36), primary_key=True),
        Column("organization_id", String(36), ForeignKey("organizations.id"), nullable=False),
        Column("contract_id", String(36), ForeignKey("contracts.id"), nullable=False),
        Column("analysis_run_id", String(36), ForeignKey("analysis_runs.id"), nullable=False),
        Column("source_result_id", String(36), ForeignKey("analysis_results.id")),
        Column("file_version_id", String(36), ForeignKey("file_versions.id"), nullable=False),
        Column(
            "template_version_id",
            String(36),
            ForeignKey("analysis_template_versions.id"),
            nullable=False,
        ),
        Column("prompt_type", String(50), nullable=False),
        Column("version", Integer, nullable=False),
        Column("status", String(20), nullable=False),
        Column("summary", Text, nullable=False),
        Column("raw_json", Text, nullable=False),
        Column("created_by", String(36), ForeignKey("users.id"), nullable=False),
        Column("reviewed_by", String(36), ForeignKey("users.id")),
        Column("review_comment", Text),
        Column("reviewed_at", DateTime(timezone=True)),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("updated_at", DateTime(timezone=True), nullable=False),
        UniqueConstraint(
            "analysis_run_id",
            "prompt_type",
            "version",
            name="uq_structured_analysis_result_version",
        ),
    )
    Table(
        "structured_analysis_fields",
        metadata,
        Column("id", String(36), primary_key=True),
        Column(
            "structured_result_id",
            String(36),
            ForeignKey("structured_analysis_results.id"),
            nullable=False,
        ),
        Column("field_key", String(128), nullable=False),
        Column("label", String(200), nullable=False),
        Column("value_text", Text, nullable=False),
        Column("value_json", Text, nullable=False),
        Column("confidence", Numeric(5, 4)),
        Column("position", Integer, nullable=False),
        Column("created_at", DateTime(timezone=True), nullable=False),
    )
    Table(
        "analysis_evidence",
        metadata,
        Column("id", String(36), primary_key=True),
        Column("organization_id", String(36), ForeignKey("organizations.id"), nullable=False),
        Column("contract_id", String(36), ForeignKey("contracts.id"), nullable=False),
        Column(
            "structured_result_id",
            String(36),
            ForeignKey("structured_analysis_results.id"),
            nullable=False,
        ),
        Column("file_version_id", String(36), ForeignKey("file_versions.id"), nullable=False),
        Column("page_no", Integer),
        Column("char_start", Integer),
        Column("char_end", Integer),
        Column("quote", Text, nullable=False),
        Column("locator_json", Text, nullable=False),
        Column("created_by", String(36), ForeignKey("users.id"), nullable=False),
        Column("created_at", DateTime(timezone=True), nullable=False),
    )
    Table(
        "analysis_risks",
        metadata,
        Column("id", String(36), primary_key=True),
        Column("organization_id", String(36), ForeignKey("organizations.id"), nullable=False),
        Column("contract_id", String(36), ForeignKey("contracts.id"), nullable=False),
        Column(
            "structured_result_id",
            String(36),
            ForeignKey("structured_analysis_results.id"),
            nullable=False,
        ),
        Column("evidence_id", String(36), ForeignKey("analysis_evidence.id")),
        Column("code", String(100)),
        Column("title", String(300), nullable=False),
        Column("description", Text, nullable=False),
        Column("severity", String(20), nullable=False),
        Column("status", String(20), nullable=False),
        Column("reviewer_comment", Text),
        Column("reviewed_by", String(36), ForeignKey("users.id")),
        Column("reviewed_at", DateTime(timezone=True)),
        Column("created_by", String(36), ForeignKey("users.id"), nullable=False),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("updated_at", DateTime(timezone=True), nullable=False),
    )
    metadata.create_all(bind=bind, checkfirst=True)

    index_specs = {
        "structured_analysis_results": (
            ("ix_structured_analysis_results_organization_id", ["organization_id"]),
            ("ix_structured_analysis_results_contract_id", ["contract_id"]),
            ("ix_structured_analysis_results_analysis_run_id", ["analysis_run_id"]),
            ("ix_structured_analysis_results_source_result_id", ["source_result_id"]),
            ("ix_structured_analysis_results_file_version_id", ["file_version_id"]),
            ("ix_structured_analysis_results_template_version_id", ["template_version_id"]),
            ("ix_structured_analysis_results_prompt_type", ["prompt_type"]),
            ("ix_structured_analysis_results_status", ["status"]),
            (
                "ix_structured_results_org_contract_status",
                ["organization_id", "contract_id", "status"],
            ),
            (
                "ix_structured_results_run_prompt",
                ["analysis_run_id", "prompt_type", "version"],
            ),
        ),
        "structured_analysis_fields": (
            ("ix_structured_analysis_fields_structured_result_id", ["structured_result_id"]),
            ("ix_structured_fields_result_position", ["structured_result_id", "position"]),
        ),
        "analysis_evidence": (
            ("ix_analysis_evidence_organization_id", ["organization_id"]),
            ("ix_analysis_evidence_contract_id", ["contract_id"]),
            ("ix_analysis_evidence_structured_result_id", ["structured_result_id"]),
            ("ix_analysis_evidence_file_version_id", ["file_version_id"]),
            ("ix_analysis_evidence_result_page", ["structured_result_id", "page_no"]),
            ("ix_analysis_evidence_org_contract", ["organization_id", "contract_id"]),
        ),
        "analysis_risks": (
            ("ix_analysis_risks_organization_id", ["organization_id"]),
            ("ix_analysis_risks_contract_id", ["contract_id"]),
            ("ix_analysis_risks_structured_result_id", ["structured_result_id"]),
            ("ix_analysis_risks_evidence_id", ["evidence_id"]),
            ("ix_analysis_risks_severity", ["severity"]),
            ("ix_analysis_risks_status", ["status"]),
            (
                "ix_analysis_risks_org_contract_status",
                ["organization_id", "contract_id", "status"],
            ),
            ("ix_analysis_risks_result_severity", ["structured_result_id", "severity"]),
        ),
    }
    for table_name, specs in index_specs.items():
        existing = {item["name"] for item in inspect(bind).get_indexes(table_name)}
        for name, columns in specs:
            if name not in existing:
                op.create_index(name, table_name, columns, unique=False)


def downgrade() -> None:
    # Restore a pre-stage7 backup instead of deleting review history.
    pass
