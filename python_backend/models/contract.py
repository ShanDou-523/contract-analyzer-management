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
    party_links = relationship("ContractParty", back_populates="contract", cascade="all, delete-orphan")
    fulfillment_tasks = relationship(
        "FulfillmentTask", back_populates="contract", cascade="all, delete-orphan"
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


class Party(Base):
    """Organization-scoped legal entity used by one or more contracts."""

    __tablename__ = "parties"
    __table_args__ = (
        UniqueConstraint("organization_id", "party_type", "name", name="uq_party_org_type_name"),
        Index("ix_parties_organization_name", "organization_id", "name"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    party_type = Column(String(20), nullable=False, default="other", index=True)
    name = Column(String(512), nullable=False)
    tax_no = Column(String(100), nullable=True)
    address = Column(String(512), nullable=True)
    phone = Column(String(100), nullable=True)
    email = Column(String(320), nullable=True)
    status = Column(String(20), nullable=False, default="active", index=True)
    metadata_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)

    contract_links = relationship("ContractParty", back_populates="party", cascade="all, delete-orphan")
    contacts = relationship("Contact", back_populates="party", cascade="all, delete-orphan")


class ContractParty(Base):
    """Role-specific association between a contract and a party."""

    __tablename__ = "contract_parties"
    __table_args__ = (
        UniqueConstraint("contract_id", "party_id", "role", name="uq_contract_party_role"),
        Index("ix_contract_parties_contract_role", "contract_id", "role"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    contract_id = Column(String(36), ForeignKey("contracts.id"), nullable=False, index=True)
    party_id = Column(String(36), ForeignKey("parties.id"), nullable=False, index=True)
    role = Column(String(20), nullable=False, default="other", index=True)
    notes = Column(Text, nullable=False, default="")
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)

    contract = relationship("Contract", back_populates="party_links")
    party = relationship("Party", back_populates="contract_links")


class Contact(Base):
    """A contact person belonging to an organization party."""

    __tablename__ = "contacts"
    __table_args__ = (Index("ix_contacts_organization_name", "organization_id", "name"),)

    id = Column(String(36), primary_key=True, default=_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    party_id = Column(String(36), ForeignKey("parties.id"), nullable=False, index=True)
    name = Column(String(200), nullable=False)
    title = Column(String(200), nullable=True)
    phone = Column(String(100), nullable=True)
    email = Column(String(320), nullable=True)
    is_primary = Column(Boolean, nullable=False, default=False, index=True)
    status = Column(String(20), nullable=False, default="active", index=True)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)

    party = relationship("Party", back_populates="contacts")


class FulfillmentTask(Base):
    """Contract obligation with a constrained status transition."""

    __tablename__ = "fulfillment_tasks"
    __table_args__ = (
        Index("ix_fulfillment_tasks_org_due", "organization_id", "due_at"),
        Index("ix_fulfillment_tasks_contract_status", "contract_id", "status"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    contract_id = Column(String(36), ForeignKey("contracts.id"), nullable=False, index=True)
    title = Column(String(300), nullable=False)
    description = Column(Text, nullable=False, default="")
    task_type = Column(String(50), nullable=False, default="other", index=True)
    status = Column(String(20), nullable=False, default="pending", index=True)
    priority = Column(String(20), nullable=False, default="medium", index=True)
    assignee_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    due_at = Column(DateTime(timezone=True), nullable=False, index=True)
    remind_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    completed_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False)
    updated_by = Column(String(36), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)

    contract = relationship("Contract", back_populates="fulfillment_tasks")
    notifications = relationship("Notification", back_populates="task")


class Notification(Base):
    """In-app reminder generated from a task or an analysis risk."""

    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_notifications_dedupe_key"),
        Index(
            "ix_notifications_org_recipient_status",
            "organization_id",
            "recipient_id",
            "status",
        ),
        Index("ix_notifications_org_task", "organization_id", "task_id"),
        Index("ix_notifications_org_risk", "organization_id", "risk_id"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    recipient_id = Column(String(36), ForeignKey("users.id"), nullable=False, index=True)
    contract_id = Column(String(36), ForeignKey("contracts.id"), nullable=False, index=True)
    task_id = Column(String(36), ForeignKey("fulfillment_tasks.id"), nullable=True, index=True)
    risk_id = Column(String(36), ForeignKey("analysis_risks.id"), nullable=True, index=True)
    notification_type = Column(String(20), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="unread", index=True)
    title = Column(String(300), nullable=False)
    message = Column(Text, nullable=False, default="")
    source_at = Column(DateTime(timezone=True), nullable=False)
    dedupe_key = Column(String(64), nullable=False)
    metadata_json = Column(Text, nullable=False, default="{}")
    generated_at = Column(DateTime(timezone=True), default=_now, nullable=False)
    read_at = Column(DateTime(timezone=True), nullable=True)
    ignored_at = Column(DateTime(timezone=True), nullable=True)

    task = relationship("FulfillmentTask", back_populates="notifications")
    risk = relationship("AnalysisRisk", back_populates="notifications")
    deliveries = relationship("NotificationDelivery", back_populates="notification")


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
    structured_results = relationship(
        "StructuredAnalysisResult",
        back_populates="analysis_run",
        cascade="all, delete-orphan",
    )


class StructuredAnalysisResult(Base):
    """Immutable, versioned structured interpretation of one analysis run."""

    __tablename__ = "structured_analysis_results"
    __table_args__ = (
        UniqueConstraint(
            "analysis_run_id",
            "prompt_type",
            "version",
            name="uq_structured_analysis_result_version",
        ),
        Index(
            "ix_structured_results_org_contract_status",
            "organization_id",
            "contract_id",
            "status",
        ),
        Index(
            "ix_structured_results_run_prompt",
            "analysis_run_id",
            "prompt_type",
            "version",
        ),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    contract_id = Column(String(36), ForeignKey("contracts.id"), nullable=False, index=True)
    analysis_run_id = Column(String(36), ForeignKey("analysis_runs.id"), nullable=False, index=True)
    source_result_id = Column(String(36), ForeignKey("analysis_results.id"), nullable=True, index=True)
    file_version_id = Column(String(36), ForeignKey("file_versions.id"), nullable=False, index=True)
    template_version_id = Column(
        String(36), ForeignKey("analysis_template_versions.id"), nullable=False, index=True
    )
    prompt_type = Column(String(50), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default="draft", index=True)
    summary = Column(Text, nullable=False, default="")
    raw_json = Column(Text, nullable=False, default="{}")
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False)
    reviewed_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    review_comment = Column(Text, nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)

    contract = relationship("Contract")
    analysis_run = relationship("AnalysisRun", back_populates="structured_results")
    source_result = relationship("AnalysisResult")
    file_version = relationship("FileVersion")
    template_version = relationship("AnalysisTemplateVersion")
    fields = relationship(
        "StructuredAnalysisField",
        back_populates="structured_result",
        cascade="all, delete-orphan",
        order_by="StructuredAnalysisField.position",
    )
    evidence = relationship(
        "AnalysisEvidence",
        back_populates="structured_result",
        cascade="all, delete-orphan",
        order_by="AnalysisEvidence.created_at",
    )
    risks = relationship(
        "AnalysisRisk",
        back_populates="structured_result",
        cascade="all, delete-orphan",
        order_by="AnalysisRisk.created_at",
    )


class StructuredAnalysisField(Base):
    __tablename__ = "structured_analysis_fields"
    __table_args__ = (Index("ix_structured_fields_result_position", "structured_result_id", "position"),)

    id = Column(String(36), primary_key=True, default=_uuid)
    structured_result_id = Column(
        String(36), ForeignKey("structured_analysis_results.id"), nullable=False, index=True
    )
    field_key = Column(String(128), nullable=False)
    label = Column(String(200), nullable=False)
    value_text = Column(Text, nullable=False, default="")
    value_json = Column(Text, nullable=False, default="null")
    confidence = Column(Numeric(5, 4), nullable=True)
    position = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)

    structured_result = relationship("StructuredAnalysisResult", back_populates="fields")


class AnalysisEvidence(Base):
    __tablename__ = "analysis_evidence"
    __table_args__ = (
        Index("ix_analysis_evidence_result_page", "structured_result_id", "page_no"),
        Index("ix_analysis_evidence_org_contract", "organization_id", "contract_id"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    contract_id = Column(String(36), ForeignKey("contracts.id"), nullable=False, index=True)
    structured_result_id = Column(
        String(36), ForeignKey("structured_analysis_results.id"), nullable=False, index=True
    )
    file_version_id = Column(String(36), ForeignKey("file_versions.id"), nullable=False, index=True)
    page_no = Column(Integer, nullable=True)
    char_start = Column(Integer, nullable=True)
    char_end = Column(Integer, nullable=True)
    quote = Column(Text, nullable=False, default="")
    locator_json = Column(Text, nullable=False, default="{}")
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)

    structured_result = relationship("StructuredAnalysisResult", back_populates="evidence")
    file_version = relationship("FileVersion")


class AnalysisRisk(Base):
    __tablename__ = "analysis_risks"
    __table_args__ = (
        Index("ix_analysis_risks_org_contract_status", "organization_id", "contract_id", "status"),
        Index("ix_analysis_risks_result_severity", "structured_result_id", "severity"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    contract_id = Column(String(36), ForeignKey("contracts.id"), nullable=False, index=True)
    structured_result_id = Column(
        String(36), ForeignKey("structured_analysis_results.id"), nullable=False, index=True
    )
    evidence_id = Column(String(36), ForeignKey("analysis_evidence.id"), nullable=True, index=True)
    code = Column(String(100), nullable=True)
    title = Column(String(300), nullable=False)
    description = Column(Text, nullable=False, default="")
    severity = Column(String(20), nullable=False, default="medium", index=True)
    status = Column(String(20), nullable=False, default="open", index=True)
    assignee_id = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    remediation_due_at = Column(DateTime(timezone=True), nullable=True, index=True)
    remediation_notes = Column(Text, nullable=True)
    reviewer_comment = Column(Text, nullable=True)
    reviewed_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    closed_by = Column(String(36), ForeignKey("users.id"), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    closure_comment = Column(Text, nullable=True)
    created_by = Column(String(36), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)

    structured_result = relationship("StructuredAnalysisResult", back_populates="risks")
    evidence = relationship("AnalysisEvidence")
    notifications = relationship("Notification", back_populates="risk")


class BackgroundJob(Base):
    """Durable organization-scoped work item processed outside request transactions."""

    __tablename__ = "background_jobs"
    __table_args__ = (
        UniqueConstraint("dedupe_key", name="uq_background_jobs_dedupe_key"),
        Index("ix_background_jobs_claim", "status", "available_at", "priority"),
        Index("ix_background_jobs_org_created", "organization_id", "created_at"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    job_type = Column(String(50), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="queued", index=True)
    priority = Column(Integer, nullable=False, default=0)
    payload_json = Column(Text, nullable=False, default="{}")
    result_json = Column(Text, nullable=False, default="{}")
    dedupe_key = Column(String(160), nullable=False)
    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=3)
    available_at = Column(DateTime(timezone=True), nullable=False, default=_now, index=True)
    locked_at = Column(DateTime(timezone=True), nullable=True, index=True)
    locked_by = Column(String(100), nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    requested_by = Column(String(36), ForeignKey("users.id"), nullable=True, index=True)
    error_code = Column(String(100), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)


class NotificationDelivery(Base):
    """Latest delivery state for one notification/provider pair."""

    __tablename__ = "notification_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "notification_id", "provider_name", name="uq_notification_delivery_provider"
        ),
        Index(
            "ix_notification_deliveries_org_status", "organization_id", "status", "updated_at"
        ),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    notification_id = Column(String(36), ForeignKey("notifications.id"), nullable=False, index=True)
    background_job_id = Column(String(36), ForeignKey("background_jobs.id"), nullable=True, index=True)
    provider_name = Column(String(50), nullable=False, default="fake", index=True)
    channel = Column(String(30), nullable=False, default="fake")
    status = Column(String(20), nullable=False, default="queued", index=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=3)
    last_error = Column(Text, nullable=True)
    provider_message_id = Column(String(200), nullable=True)
    next_retry_at = Column(DateTime(timezone=True), nullable=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)

    notification = relationship("Notification", back_populates="deliveries")


class RiskReportSnapshot(Base):
    """Daily immutable-style aggregate for historical risk trend reporting."""

    __tablename__ = "risk_report_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "snapshot_date", name="uq_risk_snapshot_org_date"
        ),
        Index("ix_risk_snapshots_org_date", "organization_id", "snapshot_date"),
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    organization_id = Column(String(36), ForeignKey("organizations.id"), nullable=False, index=True)
    snapshot_date = Column(Date, nullable=False, index=True)
    total = Column(Integer, nullable=False, default=0)
    active = Column(Integer, nullable=False, default=0)
    overdue = Column(Integer, nullable=False, default=0)
    closed = Column(Integer, nullable=False, default=0)
    critical = Column(Integer, nullable=False, default=0)
    overdue_rate = Column(Numeric(8, 4), nullable=False, default=0)
    contract_rankings_json = Column(Text, nullable=False, default="[]")
    assignee_workloads_json = Column(Text, nullable=False, default="[]")
    source_job_id = Column(String(36), ForeignKey("background_jobs.id"), nullable=True, index=True)
    generated_at = Column(DateTime(timezone=True), nullable=False, default=_now)
