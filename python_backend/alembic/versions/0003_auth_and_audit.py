"""Add authentication, role, organization-scope, and audit persistence."""

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    inspect,
)

from alembic import op

revision = "0003_auth_and_audit"
down_revision = "0002_contract_domain"
branch_labels = None
depends_on = None


def _auth_tables(metadata: MetaData) -> list[Table]:
    organizations = Table(
        "organizations",
        metadata,
        Column("id", String(36), primary_key=True),
        Column("name", String(200), nullable=False),
        Column("code", String(100), nullable=False),
        Column("status", String(20), nullable=False),
        Column("metadata_json", Text, nullable=False),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("updated_at", DateTime(timezone=True), nullable=False),
    )
    users = Table(
        "users",
        metadata,
        Column("id", String(36), primary_key=True),
        Column("organization_id", String(36), ForeignKey("organizations.id"), nullable=False),
        Column("username", String(100), nullable=False),
        Column("display_name", String(200), nullable=False),
        Column("email", String(320)),
        Column("password_hash", String(512)),
        Column("status", String(20), nullable=False),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("updated_at", DateTime(timezone=True), nullable=False),
    )
    roles = Table(
        "roles",
        metadata,
        Column("id", String(36), primary_key=True),
        Column("organization_id", String(36), ForeignKey("organizations.id")),
        Column("name", String(50), nullable=False),
        Column("description", String(300), nullable=False),
        Column("created_at", DateTime(timezone=True), nullable=False),
        UniqueConstraint("organization_id", "name", name="uq_role_org_name"),
    )
    user_roles = Table(
        "user_roles",
        metadata,
        Column("user_id", String(36), ForeignKey("users.id"), primary_key=True),
        Column("role_id", String(36), ForeignKey("roles.id"), primary_key=True),
        Column("created_at", DateTime(timezone=True), nullable=False),
    )
    auth_sessions = Table(
        "auth_sessions",
        metadata,
        Column("id", String(36), primary_key=True),
        Column("user_id", String(36), ForeignKey("users.id"), nullable=False),
        Column("organization_id", String(36), ForeignKey("organizations.id"), nullable=False),
        Column("refresh_token_hash", String(64), nullable=False, unique=True),
        Column("expires_at", DateTime(timezone=True), nullable=False),
        Column("revoked_at", DateTime(timezone=True)),
        Column("created_at", DateTime(timezone=True), nullable=False),
        Column("last_used_at", DateTime(timezone=True)),
    )
    audit_logs = Table(
        "audit_logs",
        metadata,
        Column("id", String(36), primary_key=True),
        Column("organization_id", String(36)),
        Column("user_id", String(36)),
        Column("action", String(100), nullable=False),
        Column("resource_type", String(100)),
        Column("resource_id", String(36)),
        Column("details_json", Text, nullable=False),
        Column("request_id", String(100)),
        Column("created_at", DateTime(timezone=True), nullable=False),
    )
    return [organizations, users, roles, user_roles, auth_sessions, audit_logs]


def _add_column_if_missing(bind, table_name: str, column: Column) -> None:
    current = {column_info["name"] for column_info in inspect(bind).get_columns(table_name)}
    if column.name not in current:
        op.add_column(table_name, column)


def upgrade() -> None:
    bind = op.get_bind()
    _add_column_if_missing(bind, "documents", Column("organization_id", String(36), nullable=True))
    _add_column_if_missing(
        bind, "analysis_templates", Column("organization_id", String(36), nullable=True)
    )
    _add_column_if_missing(
        bind, "users", Column("failed_login_count", Integer, nullable=False, server_default="0")
    )
    _add_column_if_missing(
        bind, "users", Column("locked_until", DateTime(timezone=True), nullable=True)
    )
    _add_column_if_missing(
        bind, "users", Column("last_login_at", DateTime(timezone=True), nullable=True)
    )

    metadata = MetaData()
    _auth_tables(metadata)
    metadata.create_all(bind=bind, checkfirst=True)

    inspector = inspect(bind)
    for table_name, columns in {
        "documents": ["organization_id"],
        "analysis_templates": ["organization_id"],
        "users": ["organization_id", "status"],
        "roles": ["organization_id"],
        "user_roles": ["user_id", "role_id"],
        "auth_sessions": [
            "user_id",
            "organization_id",
            "refresh_token_hash",
            "expires_at",
            "revoked_at",
        ],
        "audit_logs": ["organization_id", "user_id", "action", "created_at"],
    }.items():
        existing = {index["name"] for index in inspector.get_indexes(table_name)}
        for column_name in columns:
            index_name = f"ix_{table_name}_{column_name}"
            if index_name not in existing:
                op.create_index(index_name, table_name, [column_name], unique=False)


def downgrade() -> None:
    # Authentication and audit data are not dropped automatically.
    pass
