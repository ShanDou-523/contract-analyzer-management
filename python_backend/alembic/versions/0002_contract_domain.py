"""Create the initial contract-management domain tables."""

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
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

revision = "0002_contract_domain"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def _tables(metadata: MetaData) -> list[Table]:
    # Existing legacy table referenced by the new immutable template versions.
    Table("analysis_templates", metadata, Column("id", String(36), primary_key=True))
    organizations = Table(
        "organizations",
        metadata,
        Column("id", String(36), primary_key=True),
        Column("name", String(200), nullable=False),
        Column("code", String(100), nullable=False, unique=True),
        Column("status", String(20), nullable=False, default="active"),
        Column("metadata_json", Text, nullable=False, default="{}"),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("updated_at", DateTime(timezone=True), nullable=False),
    )
    users = Table(
        "users",
        metadata,
        Column("id", String(36), primary_key=True),
        Column("organization_id", String(36), ForeignKey("organizations.id"), nullable=False),
        Column("username", String(100), nullable=False, unique=True),
        Column("display_name", String(200), nullable=False, default=""),
        Column("email", String(320)),
        Column("password_hash", String(512)),
        Column("status", String(20), nullable=False, default="active"),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("updated_at", DateTime(timezone=True), nullable=False),
    )
    contracts = Table(
        "contracts",
        metadata,
        Column("id", String(36), primary_key=True),
        Column("organization_id", String(36), ForeignKey("organizations.id"), nullable=False),
        Column("legacy_document_id", String(36), unique=True),
        Column("contract_no", String(128)),
        Column("name", String(512), nullable=False),
        Column("category", String(100)),
        Column("status", String(32), nullable=False, default="draft"),
        Column("party_a_name", String(512)),
        Column("party_b_name", String(512)),
        Column("project_name", String(512)),
        Column("department_name", String(200)),
        Column("owner_id", String(36), ForeignKey("users.id")),
        Column("sign_date", Date),
        Column("effective_date", Date),
        Column("start_date", Date),
        Column("end_date", Date),
        Column("amount", Numeric(18, 2)),
        Column("currency", String(3), nullable=False, default="CNY"),
        Column("tax_included", Boolean),
        Column("risk_level", String(20), nullable=False, default="medium"),
        Column("source", String(20), nullable=False, default="manual"),
        Column("metadata_json", Text, nullable=False, default="{}"),
        Column("created_by", String(36), ForeignKey("users.id")),
        Column("updated_by", String(36), ForeignKey("users.id")),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("updated_at", DateTime(timezone=True), nullable=False),
        Column("deleted_at", DateTime(timezone=True)),
    )
    contract_files = Table(
        "contract_files",
        metadata,
        Column("id", String(36), primary_key=True),
        Column("contract_id", String(36), ForeignKey("contracts.id"), nullable=False),
        Column("purpose", String(50), nullable=False, default="original"),
        Column("current_version_id", String(36)),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("updated_at", DateTime(timezone=True), nullable=False),
        Column("deleted_at", DateTime(timezone=True)),
    )
    file_versions = Table(
        "file_versions",
        metadata,
        Column("id", String(36), primary_key=True),
        Column("contract_file_id", String(36), ForeignKey("contract_files.id"), nullable=False),
        Column("version_no", Integer, nullable=False),
        Column("original_filename", String(512), nullable=False),
        Column("storage_key", String(1024), nullable=False),
        Column("mime_type", String(128), nullable=False, default="application/pdf"),
        Column("size_bytes", Integer, nullable=False, default=0),
        Column("sha256", String(64)),
        Column("page_count", Integer),
        Column("uploaded_by", String(36), ForeignKey("users.id")),
        Column("uploaded_at", DateTime(timezone=True), nullable=False),
        Column("is_current", Boolean, nullable=False, default=True),
        Column("deleted_at", DateTime(timezone=True)),
        UniqueConstraint("contract_file_id", "version_no", name="uq_file_version_no"),
    )
    template_versions = Table(
        "analysis_template_versions",
        metadata,
        Column("id", String(36), primary_key=True),
        Column("template_id", String(36), ForeignKey("analysis_templates.id"), nullable=False),
        Column("version", Integer, nullable=False),
        Column("fields_json", Text, nullable=False, default="[]"),
        Column("analysis_focus", Text, nullable=False, default=""),
        Column("review_enabled", Boolean, nullable=False, default=True),
        Column("review_instructions", Text, nullable=False, default=""),
        Column("model_name", String(100)),
        Column("prompt_version", String(100)),
        Column("status", String(20), nullable=False, default="published"),
        Column("created_by", String(36), ForeignKey("users.id")),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("published_at", DateTime(timezone=True)),
        UniqueConstraint("template_id", "version", name="uq_analysis_template_version"),
    )
    analysis_runs = Table(
        "analysis_runs",
        metadata,
        Column("id", String(36), primary_key=True),
        Column("contract_id", String(36), ForeignKey("contracts.id"), nullable=False),
        Column("file_version_id", String(36), ForeignKey("file_versions.id")),
        Column("task_type", String(30), nullable=False, default="analysis"),
        Column("status", String(20), nullable=False, default="queued"),
        Column("requested_by", String(36), ForeignKey("users.id")),
        Column("started_at", DateTime(timezone=True)),
        Column("finished_at", DateTime(timezone=True)),
        Column("provider_name", String(100)),
        Column("model_name", String(100)),
        Column("prompt_version", String(100)),
        Column("template_version_id", String(36), ForeignKey("analysis_template_versions.id")),
        Column("retry_count", Integer, nullable=False, default=0),
        Column("error_code", String(100)),
        Column("error_message", Text),
        Column("input_chars", Integer),
        Column("input_tokens", Integer),
        Column("output_tokens", Integer),
        Column("estimated_cost", Numeric(18, 6)),
        Column("created_at", DateTime(timezone=True), nullable=False),
    )
    return [
        organizations,
        users,
        contracts,
        contract_files,
        file_versions,
        template_versions,
        analysis_runs,
    ]


def upgrade() -> None:
    metadata = MetaData()
    _tables(metadata)
    bind = op.get_bind()
    metadata.create_all(bind=bind, checkfirst=True)
    inspector = inspect(bind)
    for table_name, columns in {
        "organizations": ["status"],
        "users": ["organization_id", "status"],
        "contracts": ["organization_id", "status", "risk_level", "deleted_at"],
        "contract_files": ["contract_id", "deleted_at"],
        "file_versions": ["contract_file_id", "sha256", "is_current", "deleted_at"],
        "analysis_template_versions": ["template_id", "status"],
        "analysis_runs": ["contract_id", "status", "template_version_id"],
    }.items():
        for column_name in columns:
            if column_name not in {column["name"] for column in inspector.get_columns(table_name)}:
                continue
            if f"ix_{table_name}_{column_name}" not in {
                index["name"] for index in inspector.get_indexes(table_name)
            }:
                op.create_index(f"ix_{table_name}_{column_name}", table_name, [column_name])
    if "ix_contracts_organization_status" not in {
        index["name"] for index in inspector.get_indexes("contracts")
    }:
        op.create_index(
            "ix_contracts_organization_status",
            "contracts",
            ["organization_id", "status"],
            unique=False,
        )
    if "ix_analysis_runs_contract_created" not in {
        index["name"] for index in inspector.get_indexes("analysis_runs")
    }:
        op.create_index(
            "ix_analysis_runs_contract_created",
            "analysis_runs",
            ["contract_id", "created_at"],
            unique=False,
        )
    result_columns = {column["name"] for column in inspector.get_columns("analysis_results")}
    if "analysis_run_id" not in result_columns:
        op.add_column(
            "analysis_results",
            Column("analysis_run_id", String(36), nullable=True),
        )
        op.create_index(
            "ix_analysis_results_analysis_run_id", "analysis_results", ["analysis_run_id"]
        )


def downgrade() -> None:
    # Stage 2 data is business data; rollback is performed by restoring the backup.
    pass
