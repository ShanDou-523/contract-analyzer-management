"""Stage 9 risk reminder orchestration and organization report tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

import config
import database
import main
from alembic import command
from core import security
from models.contract import (
    AnalysisRisk,
    AnalysisRun,
    AnalysisTemplateVersion,
    Base,
    Contract,
    ContractFile,
    FileVersion,
    Organization,
    StructuredAnalysisResult,
)
from models.document import AnalysisTemplate
from services import auth_service
from services.risk_notification_service import scan_risk_reminders


def _settings(tmp_path: Path):
    data_dir = tmp_path / "data"
    return SimpleNamespace(
        environment="local",
        jwt_secret_key="stage9-test-secret",
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
        secret_key="",
        secret_key_path=data_dir / "secret.key",
    )


def test_stage9_migration_adds_risk_notification_columns(tmp_path: Path):
    database_path = tmp_path / "migration.db"
    alembic_config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(Path(__file__).parents[1] / "alembic"))
    alembic_config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    command.upgrade(alembic_config, "0009_risk_notifications_reports")
    engine = create_engine(f"sqlite:///{database_path}")
    columns = {item["name"]: item for item in inspect(engine).get_columns("notifications")}
    assert "risk_id" in columns
    assert columns["task_id"]["nullable"] is True
    with engine.connect() as connection:
        assert connection.execute(text("select version_num from alembic_version")).scalar_one() == "0009_risk_notifications_reports"
    engine.dispose()


def test_stage9_risk_reminders_reports_and_scope(tmp_path: Path, monkeypatch):
    database_path = tmp_path / "stage9.db"
    engine = create_engine(f"sqlite:///{database_path}")
    Base.metadata.create_all(engine)
    local_session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    test_settings = _settings(tmp_path)
    monkeypatch.setattr(database, "SessionLocal", local_session)
    monkeypatch.setattr(database, "DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setattr(security, "settings", test_settings)
    monkeypatch.setattr(auth_service, "settings", test_settings)
    monkeypatch.setattr(config, "settings", test_settings)

    client = TestClient(main.app)
    bootstrap = client.post(
        "/api/v1/auth/bootstrap",
        json={
            "organization_name": "阶段9组织",
            "organization_code": "stage9",
            "username": "admin",
            "password": "stage9-password",
            "display_name": "阶段9管理员",
        },
    )
    assert bootstrap.status_code == 201, bootstrap.text
    admin = bootstrap.json()["user"]
    headers = {"Authorization": f"Bearer {bootstrap.json()['access_token']}"}

    db = local_session()
    template = AnalysisTemplate(
        organization_id=admin["organization_id"], name="阶段9方案", fields_json="[]", version=1, is_default=True
    )
    contract = Contract(
        organization_id=admin["organization_id"], name="阶段9合同", contract_no="S9-001", created_by=admin["id"], updated_by=admin["id"]
    )
    db.add_all([template, contract])
    db.flush()
    template_version = AnalysisTemplateVersion(template_id=template.id, version=1, fields_json="[]", created_by=admin["id"])
    contract_file = ContractFile(contract_id=contract.id, purpose="original")
    db.add_all([template_version, contract_file])
    db.flush()
    file_version = FileVersion(
        contract_file_id=contract_file.id, version_no=1, original_filename="stage9.pdf", storage_key="stage9.pdf", mime_type="application/pdf", size_bytes=10, uploaded_by=admin["id"]
    )
    db.add(file_version)
    db.flush()
    run = AnalysisRun(contract_id=contract.id, file_version_id=file_version.id, template_version_id=template_version.id, requested_by=admin["id"], status="succeeded")
    db.add(run)
    db.flush()
    result = StructuredAnalysisResult(
        organization_id=admin["organization_id"], contract_id=contract.id, analysis_run_id=run.id, file_version_id=file_version.id,
        template_version_id=template_version.id, prompt_type="reasonability_check", version=1, status="approved", raw_json="{}", created_by=admin["id"]
    )
    db.add(result)
    db.flush()
    scan_now = datetime(2026, 8, 1, 8, tzinfo=timezone.utc)
    due_risk = AnalysisRisk(
        organization_id=admin["organization_id"], contract_id=contract.id, structured_result_id=result.id,
        title="阶段9到期风险", description="需要整改", severity="critical", status="open", created_by=admin["id"],
        assignee_id=admin["id"], remediation_due_at=scan_now + timedelta(hours=4),
    )
    overdue_risk = AnalysisRisk(
        organization_id=admin["organization_id"], contract_id=contract.id, structured_result_id=result.id,
        title="阶段9逾期风险", description="已经逾期", severity="high", status="in_progress", created_by=admin["id"],
        assignee_id=admin["id"], remediation_due_at=scan_now - timedelta(hours=4),
    )
    db.add_all([due_risk, overdue_risk])
    foreign_org = Organization(name="阶段9其他组织", code="stage9-other")
    db.add(foreign_org)
    db.flush()
    foreign_contract = Contract(
        organization_id=foreign_org.id, name="不应可见合同", contract_no="OTHER-S9", created_by=admin["id"], updated_by=admin["id"]
    )
    db.add(foreign_contract)
    db.flush()
    db.add(
        AnalysisRisk(
            organization_id=foreign_org.id, contract_id=foreign_contract.id, structured_result_id=result.id,
            title="跨组织风险", description="不可见", severity="critical", status="open", created_by=admin["id"]
        )
    )
    db.commit()

    first = scan_risk_reminders(db, admin["organization_id"], now=scan_now)
    assert first.examined_risks == 2
    assert first.created == 2
    second = scan_risk_reminders(db, admin["organization_id"], now=scan_now)
    assert second.created == 0
    assert second.skipped_existing == 2
    db.commit()
    db.close()

    notifications = client.get("/api/v1/notifications", headers=headers)
    assert notifications.status_code == 200, notifications.text
    assert notifications.json()["total"] == 2
    assert {item["notification_type"] for item in notifications.json()["items"]} == {"risk_reminder", "risk_overdue"}
    assert all(item["task_id"] is None and item["risk_id"] for item in notifications.json()["items"])

    report = client.get("/api/v1/risk-reports/overview", headers=headers, params={"days": 30})
    assert report.status_code == 200, report.text
    assert report.json()["summary"]["total"] == 2
    assert report.json()["contract_rankings"][0]["contract_no"] == "S9-001"
    rankings = client.get("/api/v1/risk-reports/contracts", headers=headers, params={"page_size": 1})
    assert rankings.status_code == 200
    assert rankings.json()["total"] == 1
    assert len(rankings.json()["items"]) == 1
    exported = client.get("/api/v1/risk-reports/export", headers=headers)
    assert exported.status_code == 200
    assert exported.headers["content-type"].startswith("text/csv")
    assert "S9-001" in exported.content.decode("utf-8-sig")

    queued = client.post("/api/v1/risks/reminders/scan", headers=headers)
    assert queued.status_code == 202
    assert queued.json() == {"status": "queued"}
    engine.dispose()
