"""Add durable batch PDF import tracking."""

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
)

from alembic import op

revision = "0011_batch_imports"
down_revision = "0010_background_jobs_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    metadata = MetaData()
    Table("organizations", metadata, Column("id", String(36), primary_key=True))
    Table("users", metadata, Column("id", String(36), primary_key=True))
    Table("documents", metadata, Column("id", String(36), primary_key=True))
    Table("background_jobs", metadata, Column("id", String(36), primary_key=True))
    batch_imports = Table(
        "batch_imports",
        metadata,
        Column("id", String(36), primary_key=True),
        Column("organization_id", String(36), ForeignKey("organizations.id"), nullable=False),
        Column("created_by", String(36), ForeignKey("users.id"), nullable=False),
        Column("template_id", String(36)),
        Column("status", String(20), nullable=False),
        Column("total_count", Integer, nullable=False),
        Column("completed_count", Integer, nullable=False),
        Column("failed_count", Integer, nullable=False),
        Column("progress", Integer, nullable=False),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("started_at", DateTime(timezone=True)),
        Column("finished_at", DateTime(timezone=True)),
        Column("updated_at", DateTime(timezone=True), nullable=False),
        Index("ix_batch_imports_organization_id", "organization_id"),
        Index("ix_batch_imports_created_by", "created_by"),
        Index("ix_batch_imports_template_id", "template_id"),
        Index("ix_batch_imports_status", "status"),
        Index("ix_batch_imports_org_created", "organization_id", "created_at"),
        Index("ix_batch_imports_org_status", "organization_id", "status"),
    )
    batch_items = Table(
        "batch_import_items",
        metadata,
        Column("id", String(36), primary_key=True),
        Column("batch_id", String(36), ForeignKey("batch_imports.id"), nullable=False),
        Column("organization_id", String(36), ForeignKey("organizations.id"), nullable=False),
        Column("document_id", String(36), ForeignKey("documents.id")),
        Column("original_filename", String(512), nullable=False),
        Column("file_size", Integer, nullable=False),
        Column("sha256", String(64), nullable=False),
        Column("status", String(20), nullable=False),
        Column("stage", String(20), nullable=False),
        Column("progress", Integer, nullable=False),
        Column("ocr_job_id", String(36), ForeignKey("background_jobs.id")),
        Column("analysis_job_id", String(36), ForeignKey("background_jobs.id")),
        Column("retry_count", Integer, nullable=False),
        Column("error_code", String(100)),
        Column("error_message", Text),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("updated_at", DateTime(timezone=True), nullable=False),
        Index("ix_batch_import_items_batch_id", "batch_id"),
        Index("ix_batch_import_items_organization_id", "organization_id"),
        Index("ix_batch_import_items_document_id", "document_id"),
        Index("ix_batch_import_items_status", "status"),
        Index("ix_batch_import_items_ocr_job_id", "ocr_job_id"),
        Index("ix_batch_import_items_analysis_job_id", "analysis_job_id"),
        Index("ix_batch_import_items_org_status", "organization_id", "status"),
        Index("ix_batch_import_items_batch_status", "batch_id", "status"),
    )
    metadata.create_all(bind=bind, tables=[batch_imports, batch_items])


def downgrade() -> None:
    # Batch history is operational evidence and is intentionally retained.
    pass
