"""Stage 11 asynchronous batch import tests."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import config
import database
import main
from core import security
from models.contract import Base, BatchImport
from models.document import AnalysisTemplate
from services import auth_service, background_worker


def _settings(tmp_path: Path):
    data_dir = tmp_path / "data"
    return SimpleNamespace(
        environment="local",
        jwt_secret_key="stage11-test-secret",
        jwt_secret_key_path=data_dir / "jwt.key",
        access_token_expire_minutes=30,
        refresh_token_expire_days=14,
        max_login_attempts=3,
        lockout_minutes=15,
        admin_username="",
        admin_password="",
        resolved_data_dir=data_dir,
        resolved_upload_dir=data_dir / "uploads",
        max_file_size_bytes=5 * 1024 * 1024,
        max_file_size_mb=5,
        secret_key="",
        secret_key_path=data_dir / "secret.key",
    )


def test_batch_import_processes_each_file_and_keeps_invalid_items(tmp_path: Path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'stage11.db'}")
    local_session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(engine)
    settings = _settings(tmp_path)
    monkeypatch.setattr(database, "SessionLocal", local_session)
    monkeypatch.setattr(database, "DATABASE_URL", f"sqlite:///{tmp_path / 'stage11.db'}")
    monkeypatch.setattr(config, "settings", settings)
    monkeypatch.setattr(security, "settings", settings)
    monkeypatch.setattr(auth_service, "settings", settings)

    client = TestClient(main.app)
    bootstrap = client.post(
        "/api/v1/auth/bootstrap",
        json={
            "organization_name": "阶段11组织",
            "organization_code": "stage11",
            "username": "admin",
            "password": "stage11-password",
            "display_name": "阶段11管理员",
        },
    )
    assert bootstrap.status_code == 201, bootstrap.text
    admin = bootstrap.json()["user"]
    headers = {"Authorization": f"Bearer {bootstrap.json()['access_token']}"}
    db = local_session()
    template = AnalysisTemplate(
        organization_id=admin["organization_id"],
        name="阶段11方案",
        fields_json='[{"key":"name","label":"名称","enabled":true}]',
        version=1,
        is_default=True,
    )
    db.add(template)
    db.commit()
    template_id = template.id
    db.close()

    def fake_ocr(db, document):
        document.status = "ocr_done"
        document.ocr_text = "合同正文"
        document.page_count = 1
        db.flush()
        return {"full_text": "合同正文", "page_count": 1, "pages": []}

    def fake_analysis(db, document, *, organization_id, user_id, template_id):
        document.status = "done"
        document.analysis_template_id = template_id
        db.flush()
        return []

    monkeypatch.setattr(background_worker, "run_batch_ocr", fake_ocr)
    monkeypatch.setattr(background_worker, "run_batch_analysis", fake_analysis)

    response = client.post(
        "/api/v1/batch-imports",
        headers=headers,
        data={"template_id": template_id},
        files=[
            ("files", ("first.pdf", b"%PDF-1.4 first", "application/pdf")),
            ("files", ("second.pdf", b"%PDF-1.4 second", "application/pdf")),
            ("files", ("notes.txt", b"not a pdf", "text/plain")),
        ],
    )
    assert response.status_code == 202, response.text
    batch = response.json()
    assert batch["total_count"] == 3
    assert batch["failed_count"] == 1
    assert sum(item["status"] == "queued" for item in batch["items"]) == 2

    first = background_worker.process_one_job(
        local_session, now=datetime.now(timezone.utc), worker_id="stage11-worker"
    )
    second = background_worker.process_one_job(
        local_session, now=datetime.now(timezone.utc), worker_id="stage11-worker"
    )
    third = background_worker.process_one_job(
        local_session, now=datetime.now(timezone.utc), worker_id="stage11-worker"
    )
    fourth = background_worker.process_one_job(
        local_session, now=datetime.now(timezone.utc), worker_id="stage11-worker"
    )
    assert first and first.job_type == background_worker.JOB_BATCH_OCR
    assert second and second.job_type == background_worker.JOB_BATCH_OCR
    assert third and third.job_type == background_worker.JOB_BATCH_ANALYSIS
    assert fourth and fourth.job_type == background_worker.JOB_BATCH_ANALYSIS

    detail = client.get(f"/api/v1/batch-imports/{batch['id']}", headers=headers)
    assert detail.status_code == 200, detail.text
    payload = detail.json()
    assert payload["status"] == "partial"
    assert payload["completed_count"] == 2
    assert payload["failed_count"] == 1
    assert payload["progress"] == 67
    assert any(item["error_code"] == "UNSUPPORTED_FILE_TYPE" for item in payload["items"])

    retry = client.post(f"/api/v1/batch-imports/{batch['id']}/retry-failed", headers=headers)
    assert retry.status_code == 200
    assert retry.json()["failed_count"] == 1
    assert retry.json()["status"] == "partial"

    db = local_session()
    assert db.query(BatchImport).count() == 1
    db.close()
    engine.dispose()
