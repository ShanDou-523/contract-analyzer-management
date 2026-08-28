"""Typed application configuration with safe local defaults."""

from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys._MEIPASS)
else:
    BASE_DIR = Path(__file__).resolve().parent

load_dotenv()


class AppSettings(BaseSettings):
    """Runtime settings loaded from environment variables and ``.env``."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    environment: Literal["local", "staging", "production"] = Field(
        default="local",
        validation_alias=AliasChoices("CONTRACT_ANALYZER_ENVIRONMENT"),
    )
    data_dir: Path | None = Field(
        default=None, validation_alias=AliasChoices("CONTRACT_ANALYZER_DATA_DIR")
    )
    database_url: str | None = Field(
        default=None, validation_alias=AliasChoices("CONTRACT_ANALYZER_DATABASE_URL")
    )
    upload_dir: Path | None = Field(
        default=None, validation_alias=AliasChoices("CONTRACT_ANALYZER_UPLOAD_DIR")
    )
    server_host: str = Field(
        default="127.0.0.1", validation_alias=AliasChoices("CONTRACT_ANALYZER_HOST")
    )
    server_port: int = Field(default=5768, validation_alias=AliasChoices("CONTRACT_ANALYZER_PORT"))
    cors_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173,null",
        validation_alias=AliasChoices("CONTRACT_ANALYZER_CORS_ORIGINS"),
    )
    secret_key: str = Field(
        default="", validation_alias=AliasChoices("CONTRACT_ANALYZER_SECRET_KEY")
    )
    redis_url: str = Field(default="", validation_alias=AliasChoices("CONTRACT_ANALYZER_REDIS_URL"))
    background_worker_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("CONTRACT_ANALYZER_BACKGROUND_WORKER_ENABLED"),
    )
    background_worker_poll_seconds: float = Field(
        default=2.0,
        ge=0.2,
        le=60,
        validation_alias=AliasChoices("CONTRACT_ANALYZER_BACKGROUND_WORKER_POLL_SECONDS"),
    )
    background_job_lock_timeout_seconds: int = Field(
        default=300,
        ge=30,
        le=3600,
        validation_alias=AliasChoices("CONTRACT_ANALYZER_BACKGROUND_JOB_LOCK_TIMEOUT_SECONDS"),
    )
    notification_provider: str = Field(
        default="fake",
        pattern=r"^[a-zA-Z0-9_-]+$",
        validation_alias=AliasChoices("CONTRACT_ANALYZER_NOTIFICATION_PROVIDER"),
    )
    jwt_secret_key: str = Field(
        default="", validation_alias=AliasChoices("CONTRACT_ANALYZER_JWT_SECRET_KEY")
    )
    access_token_expire_minutes: int = Field(
        default=30,
        validation_alias=AliasChoices("CONTRACT_ANALYZER_ACCESS_TOKEN_EXPIRE_MINUTES"),
    )
    refresh_token_expire_days: int = Field(
        default=14,
        validation_alias=AliasChoices("CONTRACT_ANALYZER_REFRESH_TOKEN_EXPIRE_DAYS"),
    )
    max_login_attempts: int = Field(
        default=5,
        validation_alias=AliasChoices("CONTRACT_ANALYZER_MAX_LOGIN_ATTEMPTS"),
    )
    lockout_minutes: int = Field(
        default=15,
        validation_alias=AliasChoices("CONTRACT_ANALYZER_LOCKOUT_MINUTES"),
    )
    admin_username: str = Field(
        default="", validation_alias=AliasChoices("CONTRACT_ANALYZER_ADMIN_USERNAME")
    )
    admin_password: str = Field(
        default="", validation_alias=AliasChoices("CONTRACT_ANALYZER_ADMIN_PASSWORD")
    )
    ocr_dpi: int = Field(
        default=300,
        validation_alias=AliasChoices("CONTRACT_ANALYZER_OCR_DPI", "OCR_DPI"),
    )
    ocr_confidence_threshold: float = Field(
        default=0.5,
        validation_alias=AliasChoices(
            "CONTRACT_ANALYZER_OCR_CONFIDENCE_THRESHOLD", "OCR_CONFIDENCE_THRESHOLD"
        ),
    )
    max_file_size_mb: int = Field(
        default=50,
        validation_alias=AliasChoices("CONTRACT_ANALYZER_MAX_FILE_SIZE_MB", "MAX_FILE_SIZE_MB"),
    )
    max_pdf_pages: int = Field(
        default=200,
        validation_alias=AliasChoices("CONTRACT_ANALYZER_MAX_PDF_PAGES", "MAX_PDF_PAGES"),
    )
    deepseek_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("DEEPSEEK_API_KEY", "CONTRACT_ANALYZER_DEEPSEEK_API_KEY"),
    )
    deepseek_base_url: str = Field(
        default="https://api.deepseek.com",
        validation_alias=AliasChoices("DEEPSEEK_BASE_URL", "CONTRACT_ANALYZER_DEEPSEEK_BASE_URL"),
    )
    deepseek_model: str = Field(
        default="deepseek-chat",
        validation_alias=AliasChoices("DEEPSEEK_MODEL", "CONTRACT_ANALYZER_DEEPSEEK_MODEL"),
    )
    deepseek_timeout_seconds: int = Field(
        default=120,
        validation_alias=AliasChoices("CONTRACT_ANALYZER_DEEPSEEK_TIMEOUT_SECONDS"),
    )
    deepseek_temperature: float = Field(
        default=0.3,
        validation_alias=AliasChoices("CONTRACT_ANALYZER_DEEPSEEK_TEMPERATURE"),
    )
    baidu_ocr_api_key: str = Field(
        default="",
        validation_alias=AliasChoices("BAIDU_OCR_API_KEY", "CONTRACT_ANALYZER_BAIDU_OCR_API_KEY"),
    )
    baidu_ocr_secret_key: str = Field(
        default="",
        validation_alias=AliasChoices(
            "BAIDU_OCR_SECRET_KEY", "CONTRACT_ANALYZER_BAIDU_OCR_SECRET_KEY"
        ),
    )

    @property
    def resolved_data_dir(self) -> Path:
        if self.data_dir:
            return self.data_dir.expanduser().resolve()
        if getattr(sys, "frozen", False):
            return Path(os.getenv("APPDATA", os.path.expanduser("~"))) / "ContractAnalyzer"
        return BASE_DIR

    @property
    def resolved_upload_dir(self) -> Path:
        return (self.upload_dir or self.resolved_data_dir / "uploads").expanduser().resolve()

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{self.resolved_data_dir / 'contract_analyzer.db'}"

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def secret_key_path(self) -> Path:
        return self.resolved_data_dir / ".contract_analyzer_secret.key"

    @property
    def jwt_secret_key_path(self) -> Path:
        return self.resolved_data_dir / ".contract_analyzer_jwt.key"


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    return AppSettings()


settings = get_settings()
USER_DATA_DIR = settings.resolved_data_dir
UPLOAD_DIR = settings.resolved_upload_dir
DB_PATH = USER_DATA_DIR / "contract_analyzer.db"
DATABASE_URL = settings.resolved_database_url
SERVER_HOST = settings.server_host
SERVER_PORT = settings.server_port

OCR_DPI = settings.ocr_dpi
OCR_CONFIDENCE_THRESHOLD = settings.ocr_confidence_threshold
MAX_FILE_SIZE_MB = settings.max_file_size_mb
MAX_FILE_SIZE_BYTES = settings.max_file_size_bytes
MAX_PDF_PAGES = settings.max_pdf_pages

DEEPSEEK_API_KEY = settings.deepseek_api_key or os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = settings.deepseek_base_url
DEEPSEEK_MODEL = settings.deepseek_model
DEEPSEEK_TIMEOUT_SECONDS = settings.deepseek_timeout_seconds
DEEPSEEK_TEMPERATURE = settings.deepseek_temperature


def ensure_runtime_dirs() -> None:
    """Create runtime directories explicitly during application startup."""
    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
