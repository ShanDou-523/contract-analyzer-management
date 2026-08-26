"""Stage 1 tests for configuration, migration, and secret handling."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from alembic.config import Config
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

import main
from alembic import command
from config import AppSettings
from database import Base
from models.document import Setting
from services import secret_service


def test_prefixed_environment_overrides(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("CONTRACT_ANALYZER_ENVIRONMENT", "staging")
    monkeypatch.setenv("CONTRACT_ANALYZER_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CONTRACT_ANALYZER_OCR_DPI", "144")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-reasoner")

    loaded = AppSettings(_env_file=None)

    assert loaded.environment == "staging"
    assert loaded.ocr_dpi == 144
    assert loaded.deepseek_model == "deepseek-reasoner"
    assert loaded.resolved_data_dir == (tmp_path / "data").resolve()


def test_empty_database_can_upgrade_to_baseline(tmp_path: Path):
    database_path = tmp_path / "migration.db"
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).parents[1] / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")

    command.upgrade(config, "head")

    engine = create_engine(f"sqlite:///{database_path}")
    tables = inspect(engine).get_table_names()
    assert "alembic_version" in tables
    assert "documents" in tables
    engine.dispose()


def test_legacy_database_receives_missing_baseline_columns(tmp_path: Path):
    database_path = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite:///{database_path}")
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE TABLE documents (id VARCHAR(36) PRIMARY KEY, "
                "original_filename VARCHAR(512) NOT NULL, stored_filename VARCHAR(512) NOT NULL, "
                "file_size INTEGER NOT NULL, status VARCHAR(20) NOT NULL, ocr_text TEXT, "
                "page_count INTEGER, ocr_pages_detail TEXT, error_message TEXT, "
                "created_at DATETIME, updated_at DATETIME)"
            )
        )
        connection.execute(
            text(
                "CREATE TABLE analysis_results (id VARCHAR(36) PRIMARY KEY, "
                "document_id VARCHAR(36) NOT NULL, prompt_type VARCHAR(50) NOT NULL, "
                "prompt_text TEXT NOT NULL, response_text TEXT, tokens_used INTEGER, "
                "created_at DATETIME)"
            )
        )

    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    config.set_main_option("script_location", str(Path(__file__).parents[1] / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    command.upgrade(config, "head")

    columns = {column["name"] for column in inspect(engine).get_columns("documents")}
    result_columns = {column["name"] for column in inspect(engine).get_columns("analysis_results")}
    assert {
        "analysis_template_id",
        "analysis_template_name",
        "analysis_template_version",
    } <= columns
    assert {
        "template_id",
        "template_name",
        "template_version",
        "fields_snapshot_json",
    } <= result_columns
    engine.dispose()


def test_secret_values_are_encrypted_and_legacy_values_migrate(tmp_path: Path, monkeypatch):
    key = Fernet.generate_key().decode("ascii")
    secret_path = tmp_path / ".contract_analyzer_secret.key"
    monkeypatch.setattr(
        secret_service,
        "settings",
        SimpleNamespace(
            secret_key=key,
            resolved_data_dir=tmp_path,
            secret_key_path=secret_path,
        ),
    )
    engine = create_engine(f"sqlite:///{tmp_path / 'secrets.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    secret_service.set_secret_setting(session, "deepseek_api_key", "sk-test-value")
    raw = Setting.get(session, "deepseek_api_key")
    assert raw.startswith(secret_service.PREFIX)
    assert secret_service.get_secret_setting(session, "deepseek_api_key") == "sk-test-value"

    Setting.set(session, "baidu_ocr_api_key", "legacy-plaintext")
    assert secret_service.migrate_legacy_secrets(session) == 1
    assert Setting.get(session, "baidu_ocr_api_key").startswith(secret_service.PREFIX)
    assert secret_service.get_secret_setting(session, "baidu_ocr_api_key") == "legacy-plaintext"

    session.close()
    engine.dispose()


def test_error_response_has_stable_shape_and_request_id():
    response = TestClient(main.app).get(
        "/api/route-that-does-not-exist",
        headers={"X-Request-ID": "stage1-test-request"},
    )

    assert response.status_code == 404
    assert response.json() == {
        "code": "HTTP_404",
        "message": "Not Found",
        "details": None,
        "request_id": "stage1-test-request",
    }
    assert response.headers["X-Request-ID"] == "stage1-test-request"
