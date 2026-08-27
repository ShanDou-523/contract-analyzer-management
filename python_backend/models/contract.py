"""Stage 2 contract-management domain models.

The legacy ``documents`` tables remain in place for compatibility. These
models provide stable identities for organizations, contracts, file versions,
template versions, and historical analysis runs.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(200), nullable=False)
    code = Column(String(100), nullable=False, unique=True)
    status = Column(String(20), nullable=False, default="active", index=True)
    metadata_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)

    users = relationship("User", back_populates="organization")
    contracts = relationship("Contract", back_populates="organization")


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    username = Column(String(100), nullable=False, unique=True)
    display_name = Column(String(200), nullable=False, default="")
    email = Column(String(320), nullable=True)
    password_hash = Column(String(512), nullable=True)
    status = Column(String(20), nullable=False, default="active", index=True)
    failed_login_count = Column(Integer, nullable=False, default=0)
    locked_until = Column(DateTime(timezone=True), nullable=True)
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)

    organization = relationship("Organization", back_populates="users")
    roles = relationship("UserRole", back_populates="user", cascade="all, delete-orphan")


class Role(Base):
    __tablename__ = "roles"
    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_role_org_name"),)

    id = Column(String(36), primary_key=True, default=_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=True, index=True)
    name = Column(String(50), nullable=False)
    description = Column(String(300), nullable=False, default="")
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)

    user_roles = relationship("UserRole", back_populates="role", cascade="all, delete-orphan")


class UserRole(Base):
    __tablename__ = "user_roles"

    user_id = Column(String(36), ForeignKey("users.id"), primary_key=True)
    role_id = Column(String(36), ForeignKey("roles.id"), primary_key=True)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)

    user = relationship("User", back_populates="roles")
    role = relationship("Role", back_populates="user_roles")


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id = Column(String(36), primary_key=True, default=_uuid)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    refresh_token_hash = Column(String(64), nullable=False, unique=True, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)
    last_used_at = Column(DateTime(timezone=True), nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (Index("ix_audit_logs_org_created", "organization_id", "created_at"),)

    id = Column(String(36), primary_key=True, default=_uuid)
    organization_id = Column(String(36), nullable=True, index=True)
    user_id = Column(String(36), nullable=True, index=True)
    action = Column(String(100), nullable=False, index=True)
    resource_type = Column(String(100), nullable=True)
    resource_id = Column(String(36), nullable=True)
    details_json = Column(Text, nullable=False, default="{}")
    request_id = Column(String(100), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False, index=True)


class Contract(Base):
    __tablename__ = "contracts"
    __table_args__ = (
        Index("ix_contracts_organization_status", "organization_id", "status"),
        Index("ix_contracts_organization_contract_no", "organization_id", "contract_no"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    legacy_document_id = Column(String(36), nullable=True, unique=True, index=True)
    contract_no = Column(String(128), nullable=True)
    name = Column(String(512), nullable=False)
    category = Column(String(100), nullable=True)
    status = Column(String(32), nullable=False, default="draft", index=True)
    party_a_name = Column(String(512), nullable=True)
    party_b_name = Column(String(512), nullable=True)
    project_name = Column(String(512), nullable=True)
    department_name = Column(String(200), nullable=True)
    owner_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    sign_date = Column(Date, nullable=True)
    effective_date = Column(Date, nullable=True)
    start_date = Column(Date, nullable=True)
    end_date = Column(Date, nullable=True)
    amount = Column(Numeric(18, 2), nullable=True)
    currency = Column(String(3), nullable=False, default="CNY")
    tax_included = Column(Boolean, nullable=True)
    risk_level = Column(String(20), nullable=False, default="medium", index=True)
    source = Column(String(20), nullable=False, default="manual")
    metadata_json = Column(Text, nullable=False, default="{}")
    created_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    updated_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)

    organization = relationship("Organization", back_populates="contracts")
    files = relationship("ContractFile", back_populates="contract", cascade="all, delete-orphan")
    analysis_runs = relationship(
        "AnalysisRun", back_populates="contract", cascade="all, delete-orphan"
    )


class ContractFile(Base):
    __tablename__ = "contract_files"

    id = Column(String(36), primary_key=True, default=_uuid)
    contract_id = Column(String(36), ForeignKey("contracts.id"), nullable=False, index=True)
    purpose = Column(String(50), nullable=False, default="original")
    current_version_id = Column(String(36), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)

    contract = relationship("Contract", back_populates="files")
    versions = relationship(
        "FileVersion", back_populates="contract_file", cascade="all, delete-orphan"
    )


class FileVersion(Base):
    __tablename__ = "file_versions"
    __table_args__ = (
        UniqueConstraint("contract_file_id", "version_no", name="uq_file_version_no"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    contract_file_id = Column(
        String(36), ForeignKey("contract_files.id"), nullable=False, index=True
    )
    version_no = Column(Integer, nullable=False)
    original_filename = Column(String(512), nullable=False)
    storage_key = Column(String(1024), nullable=False)
    mime_type = Column(String(128), nullable=False, default="application/pdf")
    size_bytes = Column(Integer, nullable=False, default=0)
    sha256 = Column(String(64), nullable=True, index=True)
    page_count = Column(Integer, nullable=True)
    uploaded_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    uploaded_at = Column(DateTime(timezone=True), default=_now, nullable=False)
    is_current = Column(Boolean, nullable=False, default=True, index=True)
    deleted_at = Column(DateTime(timezone=True), nullable=True, index=True)

    contract_file = relationship("ContractFile", back_populates="versions")


class ContractImportJob(Base):
    """Staged spreadsheet import; rows are committed only after validation."""

    __tablename__ = "contract_import_jobs"

    id = Column(String(36), primary_key=True, default=_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    original_filename = Column(String(512), nullable=False)
    file_format = Column(String(16), nullable=False)
    storage_key = Column(String(1024), nullable=True)
    rows_json = Column(Text, nullable=False, default="[]")
    columns_json = Column(Text, nullable=False, default="[]")
    validation_json = Column(Text, nullable=False, default="{}")
    status = Column(String(20), nullable=False, default="uploaded", index=True)
    row_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)
    validated_at = Column(DateTime(timezone=True), nullable=True)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True, index=True)


class AnalysisTemplateVersion(Base):
    __tablename__ = "analysis_template_versions"
    __table_args__ = (
        UniqueConstraint("template_id", "version", name="uq_analysis_template_version"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    template_id = Column(
        String(36), ForeignKey("analysis_templates.id"), nullable=False, index=True
    )
    version = Column(Integer, nullable=False)
    fields_json = Column(Text, nullable=False, default="[]")
    analysis_focus = Column(Text, nullable=False, default="")
    review_enabled = Column(Boolean, nullable=False, default=True)
    review_instructions = Column(Text, nullable=False, default="")
    model_name = Column(String(100), nullable=True)
    prompt_version = Column(String(100), nullable=True)
    status = Column(String(20), nullable=False, default="published", index=True)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)
    published_at = Column(DateTime(timezone=True), nullable=True)

    template = relationship("AnalysisTemplate")


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"
    __table_args__ = (Index("ix_analysis_runs_contract_created", "contract_id", "created_at"),)

    id = Column(String(36), primary_key=True, default=_uuid)
    contract_id = Column(String(36), ForeignKey("contracts.id"), nullable=False, index=True)
    file_version_id = Column(String(36), ForeignKey("file_versions.id"), nullable=True, index=True)
    task_type = Column(String(30), nullable=False, default="analysis")
    status = Column(String(20), nullable=False, default="queued", index=True)
    requested_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    provider_name = Column(String(100), nullable=True)
    model_name = Column(String(100), nullable=True)
    prompt_version = Column(String(100), nullable=True)
    template_version_id = Column(
        String(36), ForeignKey("analysis_template_versions.id"), nullable=True, index=True
    )
    retry_count = Column(Integer, nullable=False, default=0)
    error_code = Column(String(100), nullable=True)
    error_message = Column(Text, nullable=True)
    input_chars = Column(Integer, nullable=True)
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    estimated_cost = Column(Numeric(18, 6), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)

    contract = relationship("Contract", back_populates="analysis_runs")
    file_version = relationship("FileVersion")
    template_version = relationship("AnalysisTemplateVersion")
