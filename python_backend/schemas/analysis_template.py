"""Schemas for reusable contract analysis templates."""

import re
import uuid
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class AnalysisField(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    key: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=50)
    instruction: str = Field(default="", max_length=300)
    enabled: bool = True

    @field_validator("key")
    @classmethod
    def validate_key(cls, value: str) -> str:
        value = value.strip()
        if not re.fullmatch(r"[a-z][a-z0-9_]*", value):
            raise ValueError("字段标识只能使用小写字母、数字和下划线，且必须以字母开头")
        return value

    @field_validator("label", "instruction")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class AnalysisTemplateWrite(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    analysis_focus: str = Field(default="", max_length=2000)
    fields: list[AnalysisField] = Field(min_length=1, max_length=50)
    review_enabled: bool = True
    review_instructions: str = Field(default="", max_length=4000)

    @field_validator("name", "description", "analysis_focus", "review_instructions")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def validate_fields(self):
        keys = [field.key for field in self.fields]
        labels = [field.label for field in self.fields]
        if len(keys) != len(set(keys)):
            raise ValueError("字段标识不能重复")
        if len(labels) != len(set(labels)):
            raise ValueError("字段名称不能重复")
        if not any(field.enabled for field in self.fields):
            raise ValueError("至少需要启用一个输出字段")
        return self


class AnalysisTemplateOut(AnalysisTemplateWrite):
    id: str
    version: int
    is_default: bool
    document_count: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
