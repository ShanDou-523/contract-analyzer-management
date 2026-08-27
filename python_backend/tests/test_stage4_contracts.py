"""Stage 4 contract ledger, file version, and staged import tests."""

from __future__ import annotations

import io
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import config
import database
import main
from core import security
from models.contract import Base, Contract, ContractFile, ContractImportJob, FileVersion
from routers import contracts as contracts_router
from services import auth_service, file_service


def _settings(tmp_path: Path):
    data_dir = tmp_path / "data"
    upload_dir = data_dir / "uploads"
    return SimpleNamespace(
        environment="local",
        jwt_secret_key="stage4-test-secret",
        jwt_secret_key_path=data_dir / "jwt.key",
        access_token_expire_minutes=30,
        refresh_token_expire_days=14,
        max_login_attempts=3,
        lockout_minutes=15,
        admin_username="",
        admin_password="",
        resolved_data_dir=data_dir,
        resolved_upload_dir=upload_dir,
        max_file_size_bytes=5 * 1024 * 1024,
        secret_key="",
        secret_key_path=data_dir / "secret.key",
    )


def test_contract_files_recycle_bin_and_import_flow(tmp_path: Path, monkeypatch):
    database_path = tmp_path / "stage4.db"
    engine = create_engine(f"sqlite:///{database_path}")
    Base.metadata.create_all(engine)
    local_session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    test_settings = _settings(tmp_path)
    monkeypatch.setattr(database, "SessionLocal", local_session)
    monkeypatch.setattr(database, "DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setattr(security, "settings", test_settings)
    monkeypatch.setattr(auth_service, "settings", test_settings)
    monkeypatch.setattr(config, "settings", test_settings)
    monkeypatch.setattr(file_service, "settings", test_settings)
    monkeypatch.setattr(contracts_router, "settings", test_settings)

    client = TestClient(main.app)
    bootstrap = client.post(
        "/api/v1/auth/bootstrap",
        json={
            "organization_name": "阶段4组织",
            "organization_code": "stage4",
            "username": "admin",
            "password": "stage4-password",
            "display_name": "阶段4管理员",
        },
    )
    assert bootstrap.status_code == 201, bootstrap.text
    headers = {"Authorization": f"Bearer {bootstrap.json()['access_token']}"}

    created = client.post(
        "/api/v1/contracts",
        headers=headers,
        json={"contract_no": "S4-001", "name": "文件版本合同", "status": "active"},
    )
    assert created.status_code == 201, created.text
    contract_id = created.json()["id"]

    upload = client.post(
        f"/api/v1/contracts/{contract_id}/files",
        headers=headers,
        files={"file": ("合同.pdf", b"%PDF-stage4-content", "application/pdf")},
    )
    assert upload.status_code == 201, upload.text
    version = upload.json()
    assert version["version_no"] == 1
    assert client.get(version["download_url"], headers=headers).content == b"%PDF-stage4-content"
    assert client.get(version["preview_url"], headers=headers).headers["content-type"] == "application/pdf"

    duplicate = client.post(
        f"/api/v1/contracts/{contract_id}/files",
        headers=headers,
        files={"file": ("副本.pdf", b"%PDF-stage4-content", "application/pdf")},
    )
    assert duplicate.status_code == 409
    assert not list((test_settings.resolved_upload_dir / "contract-files").glob("*.part"))

    deleted = client.delete(f"/api/v1/contracts/{contract_id}", headers=headers)
    assert deleted.status_code == 200
    assert client.get("/api/v1/contracts", headers=headers).json()["total"] == 0
    assert client.get("/api/v1/contracts/recycle-bin", headers=headers).json()["total"] == 1
    restored = client.post(f"/api/v1/contracts/{contract_id}/restore", headers=headers)
    assert restored.status_code == 200
    assert client.get("/api/v1/contracts", headers=headers).json()["total"] == 1

    csv_content = "合同编号,合同名称,甲方,金额,签署日期\nS4-002,导入合同,甲方公司,1200.50,2026-01-02\n"
    imported = client.post(
        "/api/v1/contracts/imports",
        headers=headers,
        files={"file": ("contracts.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")},
    )
    assert imported.status_code == 201, imported.text
    job_id = imported.json()["id"]
    assert imported.json()["row_count"] == 1
    preview = client.get(f"/api/v1/contracts/imports/{job_id}", headers=headers)
    assert preview.status_code == 200
    assert preview.json()["sample_rows"][0]["name"] == "导入合同"
    validated = client.post(f"/api/v1/contracts/imports/{job_id}/validate", headers=headers)
    assert validated.status_code == 200
    assert validated.json()["validation"]["valid"] is True
    confirmed = client.post(f"/api/v1/contracts/imports/{job_id}/confirm", headers=headers)
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["created_count"] == 1
    repeated = client.post(f"/api/v1/contracts/imports/{job_id}/confirm", headers=headers)
    assert repeated.status_code == 409

    invalid = client.post(
        "/api/v1/contracts/imports",
        headers=headers,
        files={
            "file": (
                "invalid.csv",
                "合同编号,合同名称\nS4-001,重复编号".encode("utf-8"),
                "text/csv",
            )
        },
    )
    invalid_job_id = invalid.json()["id"]
    invalid_check = client.post(
        f"/api/v1/contracts/imports/{invalid_job_id}/validate", headers=headers
    )
    assert invalid_check.status_code == 200
    assert invalid_check.json()["validation"]["valid"] is False
    assert client.post(
        f"/api/v1/contracts/imports/{invalid_job_id}/confirm", headers=headers
    ).status_code == 409

    db = local_session()
    assert db.query(Contract).count() == 2
    assert db.query(ContractFile).count() == 1
    assert db.query(FileVersion).count() == 1
    assert db.query(ContractImportJob).count() == 2
    db.close()
    engine.dispose()
