"""Contract management API schemas."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ContractCreate(BaseModel):
    contract_no: str | None = Field(default=None, max_length=128)
    name: str = Field(min_length=1, max_length=512)
    category: str | None = Field(default=None, max_length=100)
    party_a_name: str | None = Field(default=None, max_length=512)
    party_b_name: str | None = Field(default=None, max_length=512)
    project_name: str | None = Field(default=None, max_length=512)
    department_name: str | None = Field(default=None, max_length=200)
    sign_date: date | None = None
    effective_date: date | None = None
    start_date: date | None = None
    end_date: date | None = None
    amount: Decimal | None = Field(default=None, ge=0, max_digits=18, decimal_places=2)
    currency: str = Field(default="CNY", min_length=3, max_length=3)
    tax_included: bool | None = None
    status: str = Field(default="draft", pattern=r"^(draft|active|expired|terminated)$")
    risk_level: str = Field(default="medium", pattern=r"^(low|medium|high|critical)$")


class ContractOut(ContractCreate):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    status: str
    source: str
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


class PagedContracts(BaseModel):
    items: list[ContractOut]
    total: int
    page: int
    page_size: int


class FileVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    contract_file_id: str
    version_no: int
    original_filename: str
    mime_type: str
    size_bytes: int
    sha256: str | None = None
    page_count: int | None = None
    uploaded_at: datetime
    is_current: bool
    download_url: str
    preview_url: str


class ContractFileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    contract_id: str
    purpose: str
    current_version_id: str | None = None
    versions: list[FileVersionOut]


class ContractImportPreview(BaseModel):
    id: str
    original_filename: str
    file_format: str
    columns: list[str]
    sample_rows: list[dict[str, str]]
    row_count: int
    status: str
    validation: dict
    expires_at: datetime | None = None


class ContractImportConfirmOut(BaseModel):
    job_id: str
    created_count: int
    contract_ids: list[str]
