"""Adopt the recovered schema as the first migration revision."""

from sqlalchemy import Column, Integer, String, Text, inspect

from alembic import op
from database import Base
from models import document  # noqa: F401 - register ORM models

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)

    # The recovered application may have a database created before template
    # assignment was added. Add those columns without dropping any history.
    expected_columns = {
        "analysis_results": {
            "template_id": Column("template_id", String(36), nullable=True),
            "template_name": Column("template_name", String(100), nullable=True),
            "template_version": Column("template_version", Integer, nullable=True),
            "fields_snapshot_json": Column("fields_snapshot_json", Text, nullable=True),
        },
        "documents": {
            "analysis_template_id": Column("analysis_template_id", String(36), nullable=True),
            "analysis_template_name": Column("analysis_template_name", String(100), nullable=True),
            "analysis_template_version": Column(
                "analysis_template_version", Integer, nullable=True
            ),
        },
    }
    inspector = inspect(bind)
    for table_name, columns in expected_columns.items():
        current = {column["name"] for column in inspector.get_columns(table_name)}
        for column_name, column in columns.items():
            if column_name not in current:
                op.add_column(table_name, column)

    index_names = {index["name"] for index in inspect(bind).get_indexes("documents")}
    if "ix_documents_analysis_template_id" not in index_names:
        op.create_index(
            "ix_documents_analysis_template_id",
            "documents",
            ["analysis_template_id"],
            unique=False,
        )


def downgrade() -> None:
    # The baseline must not drop recovered user data.
    pass
