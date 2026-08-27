"""Schemas for contract parties, contacts, fulfillment tasks, and details."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from schemas.contracts import ContractFileOut, ContractOut

PartyType = Literal["party_a", "party_b", "other"]
PartyRole = Literal["party_a", "party_b", "other"]
TaskStatus = Literal["pending", "in_progress", "completed", "cancelled"]
TaskPriority = Literal["low", "medium", "high", "critical"]


class FulfillmentAssigneeOut(BaseModel):
    id: str
    display_name: str


class PartyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=512)
    party_type: PartyType = "other"
    tax_no: str | None = Field(default=None, max_length=100)
    address: str | None = Field(default=None, max_length=512)
    phone: str | None = Field(default=None, max_length=100)
    email: str | None = Field(default=None, max_length=320)


class PartyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=512)
    party_type: PartyType | None = None
    tax_no: str | None = Field(default=None, max_length=100)
    address: str | None = Field(default=None, max_length=512)
    phone: str | None = Field(default=None, max_length=100)
    email: str | None = Field(default=None, max_length=320)
    status: Literal["active", "disabled"] | None = None


class PartyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    party_type: PartyType
    name: str
    tax_no: str | None = None
    address: str | None = None
    phone: str | None = None
    email: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime


class ContactCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    title: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=100)
    email: str | None = Field(default=None, max_length=320)
    is_primary: bool = False


class ContactUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    title: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=100)
    email: str | None = Field(default=None, max_length=320)
    is_primary: bool | None = None
    status: Literal["active", "disabled"] | None = None


class ContactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    party_id: str
    name: str
    title: str | None = None
    phone: str | None = None
    email: str | None = None
    is_primary: bool
    status: str
    created_at: datetime
    updated_at: datetime


class ContractPartyLinkCreate(BaseModel):
    party_id: str
    role: PartyRole = "other"
    notes: str = Field(default="", max_length=2000)


class ContractPartyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    contract_id: str
    role: PartyRole
    notes: str
    party: PartyOut
    contacts: list[ContactOut]


class FulfillmentTaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(default="", max_length=5000)
    task_type: str = Field(default="other", min_length=1, max_length=50)
    priority: TaskPriority = "medium"
    assignee_id: str | None = None
    due_at: datetime
    remind_at: datetime | None = None


class FulfillmentTaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    task_type: str | None = Field(default=None, min_length=1, max_length=50)
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    assignee_id: str | None = None
    due_at: datetime | None = None
    remind_at: datetime | None = None
    completed_at: datetime | None = None


class FulfillmentTaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: str
    contract_id: str
    title: str
    description: str
    task_type: str
    status: TaskStatus
    priority: TaskPriority
    assignee_id: str | None = None
    due_at: datetime
    remind_at: datetime | None = None
    completed_at: datetime | None = None
    completed_by: str | None = None
    created_by: str
    updated_by: str
    created_at: datetime
    updated_at: datetime
    is_overdue: bool = False


class ContractOperationOut(BaseModel):
    id: str
    action: str
    resource_type: str | None = None
    resource_id: str | None = None
    details: dict
    user_id: str | None = None
    created_at: datetime


class ContractDetailOut(BaseModel):
    contract: ContractOut
    files: list[ContractFileOut]
    parties: list[ContractPartyOut]
    tasks: list[FulfillmentTaskOut]
    operations: list[ContractOperationOut]
