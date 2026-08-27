"""Add contract parties, contacts, fulfillment tasks, and detail indexes."""

from sqlalchemy import (
    Boolean,
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

revision = "0005_parties_and_fulfillment"
down_revision = "0004_contract_import_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    metadata = MetaData()
    Table("organizations", metadata, Column("id", String(36), primary_key=True))
    Table("users", metadata, Column("id", String(36), primary_key=True))
    Table("contracts", metadata, Column("id", String(36), primary_key=True))
    Table(
        "parties",
        metadata,
        Column("id", String(36), primary_key=True),
        Column("organization_id", String(36), ForeignKey("organizations.id"), nullable=False),
        Column("party_type", String(20), nullable=False),
        Column("name", String(512), nullable=False),
        Column("tax_no", String(100)),
        Column("address", String(512)),
        Column("phone", String(100)),
        Column("email", String(320)),
        Column("status", String(20), nullable=False),
        Column("metadata_json", Text, nullable=False),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("updated_at", DateTime(timezone=True), nullable=False),
        UniqueConstraint("organization_id", "party_type", "name", name="uq_party_org_type_name"),
    )
    Table(
        "contract_parties",
        metadata,
        Column("id", String(36), primary_key=True),
        Column("contract_id", String(36), ForeignKey("contracts.id"), nullable=False),
        Column("party_id", String(36), ForeignKey("parties.id"), nullable=False),
        Column("role", String(20), nullable=False),
        Column("notes", Text, nullable=False),
        Column("created_at", DateTime(timezone=True), nullable=False),
        UniqueConstraint("contract_id", "party_id", "role", name="uq_contract_party_role"),
    )
    Table(
        "contacts",
        metadata,
        Column("id", String(36), primary_key=True),
        Column("organization_id", String(36), ForeignKey("organizations.id"), nullable=False),
        Column("party_id", String(36), ForeignKey("parties.id"), nullable=False),
        Column("name", String(200), nullable=False),
        Column("title", String(200)),
        Column("phone", String(100)),
        Column("email", String(320)),
        Column("is_primary", Boolean, nullable=False),
        Column("status", String(20), nullable=False),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("updated_at", DateTime(timezone=True), nullable=False),
    )
    Table(
        "fulfillment_tasks",
        metadata,
        Column("id", String(36), primary_key=True),
        Column("organization_id", String(36), ForeignKey("organizations.id"), nullable=False),
        Column("contract_id", String(36), ForeignKey("contracts.id"), nullable=False),
        Column("title", String(300), nullable=False),
        Column("description", Text, nullable=False),
        Column("task_type", String(50), nullable=False),
        Column("status", String(20), nullable=False),
        Column("priority", String(20), nullable=False),
        Column("assignee_id", String(36), ForeignKey("users.id")),
        Column("due_at", DateTime(timezone=True), nullable=False),
        Column("remind_at", DateTime(timezone=True)),
        Column("completed_at", DateTime(timezone=True)),
        Column("completed_by", String(36), ForeignKey("users.id")),
        Column("created_by", String(36), ForeignKey("users.id"), nullable=False),
        Column("updated_by", String(36), ForeignKey("users.id"), nullable=False),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("updated_at", DateTime(timezone=True), nullable=False),
    )
    metadata.create_all(bind=bind, checkfirst=True)
    for table, columns in {
        "parties": ("organization_id", "party_type", "status"),
        "contract_parties": ("contract_id", "party_id", "role"),
        "contacts": ("organization_id", "party_id", "is_primary", "status"),
        "fulfillment_tasks": ("organization_id", "contract_id", "status", "priority", "due_at", "assignee_id"),
    }.items():
        indexes = {item["name"] for item in inspect(bind).get_indexes(table)}
        for column in columns:
            name = f"ix_{table}_{column}"
            if name not in indexes:
                op.create_index(name, table, [column], unique=False)
    for name, table, columns in (
        ("ix_parties_organization_name", "parties", ["organization_id", "name"]),
        ("ix_fulfillment_tasks_org_due", "fulfillment_tasks", ["organization_id", "due_at"]),
        ("ix_fulfillment_tasks_contract_status", "fulfillment_tasks", ["contract_id", "status"]),
        ("ix_contract_parties_contract_role", "contract_parties", ["contract_id", "role"]),
    ):
        if name not in {item["name"] for item in inspect(bind).get_indexes(table)}:
            op.create_index(name, table, columns, unique=False)


def downgrade() -> None:
    # Restore a pre-stage5 backup instead of dropping business history.
    pass
