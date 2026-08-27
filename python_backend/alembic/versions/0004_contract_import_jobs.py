"""Add staged contract import jobs."""

from sqlalchemy import Column, DateTime, ForeignKey, Integer, MetaData, String, Table, Text, inspect

from alembic import op

revision = "0004_contract_import_jobs"
down_revision = "0003_auth_and_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    metadata = MetaData()
    Table("organizations", metadata, Column("id", String(36), primary_key=True))
    Table("users", metadata, Column("id", String(36), primary_key=True))
    Table(
        "contract_import_jobs",
        metadata,
        Column("id", String(36), primary_key=True),
        Column("organization_id", String(36), ForeignKey("organizations.id"), nullable=False),
        Column("created_by", String(36), ForeignKey("users.id"), nullable=False),
        Column("original_filename", String(512), nullable=False),
        Column("file_format", String(16), nullable=False),
        Column("storage_key", String(1024)),
        Column("rows_json", Text, nullable=False, default="[]"),
        Column("columns_json", Text, nullable=False, default="[]"),
        Column("validation_json", Text, nullable=False, default="{}"),
        Column("status", String(20), nullable=False, default="uploaded"),
        Column("row_count", Integer, nullable=False, default=0),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("validated_at", DateTime(timezone=True)),
        Column("confirmed_at", DateTime(timezone=True)),
        Column("expires_at", DateTime(timezone=True)),
    )
    metadata.create_all(bind=bind, checkfirst=True)
    inspector = inspect(bind)
    indexes = {item["name"] for item in inspector.get_indexes("contract_import_jobs")}
    for column in ("organization_id", "created_by", "status", "expires_at"):
        name = f"ix_contract_import_jobs_{column}"
        if name not in indexes:
            op.create_index(name, "contract_import_jobs", [column], unique=False)


def downgrade() -> None:
    # Import rows can contain business data; restore a pre-stage4 backup instead.
    pass
