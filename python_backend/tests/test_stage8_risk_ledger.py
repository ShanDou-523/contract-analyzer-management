"""Stage 8 risk ledger, remediation workflow, and organization-scope tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
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
    AuditLog,
    Base,
    Contract,
    ContractFile,
    FileVersion,
    Organization,
    StructuredAnalysisResult,
)
from models.document import AnalysisTemplate
from services import auth_service


def _settings(tmp_path: Path):
    data_dir = tmp_path / "data"
    return SimpleNamespace(
        environment="local",
        jwt_secret_key="stage8-test-secret",
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


def test_stage8_migration_adds_remediation_columns(tmp_path: Path):
    database_path = tmp_path / "migration.db"
    alembic_config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(Path(__file__).parents[1] / "alembic"))
    alembic_config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    command.upgrade(alembic_config, "head")
    engine = create_engine(f"sqlite:///{database_path}")
    columns = {item["name"] for item in inspect(engine).get_columns("analysis_risks")}
    assert {
        "assignee_id",
        "remediation_due_at",
        "remediation_notes",
        "closed_by",
        "closed_at",
        "closure_comment",
    } <= columns
    engine.dispose()


def test_stage8_risk_ledger_lifecycle_scope_and_audit(tmp_path: Path, monkeypatch):
    database_path = tmp_path / "stage8.db"
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
            "organization_name": "阶段8组织",
            "organization_code": "stage8",
            "username": "admin",
            "password": "stage8-password",
            "display_name": "阶段8管理员",
        },
    )
    assert bootstrap.status_code == 201, bootstrap.text
    admin = bootstrap.json()["user"]
    headers = {"Authorization": f"Bearer {bootstrap.json()['access_token']}"}

    db = local_session()
    template = AnalysisTemplate(
        organization_id=admin["organization_id"],
        name="阶段8方案",
        fields_json="[]",
        version=1,
        is_default=True,
    )
    contract = Contract(
        organization_id=admin["organization_id"],
        name="阶段8合同",
        contract_no="S8-001",
        created_by=admin["id"],
        updated_by=admin["id"],
    )
    db.add_all([template, contract])
    db.flush()
    template_version = AnalysisTemplateVersion(
        template_id=template.id,
        version=1,
        fields_json="[]",
        created_by=admin["id"],
    )
    contract_file = ContractFile(contract_id=contract.id, purpose="original")
    db.add_all([template_version, contract_file])
    db.flush()
    file_version = FileVersion(
        contract_file_id=contract_file.id,
        version_no=1,
        original_filename="stage8.pdf",
        storage_key="stage8.pdf",
        mime_type="application/pdf",
        size_bytes=10,
        uploaded_by=admin["id"],
    )
    db.add(file_version)
    db.flush()
    run = AnalysisRun(
        contract_id=contract.id,
        file_version_id=file_version.id,
        template_version_id=template_version.id,
        requested_by=admin["id"],
        task_type="analysis",
        status="succeeded",
    )
    db.add(run)
    db.flush()
    result = StructuredAnalysisResult(
        organization_id=admin["organization_id"],
        contract_id=contract.id,
        analysis_run_id=run.id,
        file_version_id=file_version.id,
        template_version_id=template_version.id,
        prompt_type="reasonability_check",
        version=1,
        status="approved",
        summary="风险复核完成",
        raw_json="{}",
        created_by=admin["id"],
    )
    risk = AnalysisRisk(
        organization_id=admin["organization_id"],
        contract_id=contract.id,
        structured_result_id=result.id,
        title="付款期限过长",
        description="需要确认资金计划",
        severity="high",
        status="open",
        created_by=admin["id"],
        remediation_due_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    db.add(result)
    db.flush()
    risk.structured_result_id = result.id
    db.add(risk)
    foreign_org = Organization(name="其他组织", code="stage8-other")
    foreign_contract = Contract(
        organization_id=foreign_org.id,
        name="其他组织合同",
        contract_no="OTHER-001",
        created_by=admin["id"],
        updated_by=admin["id"],
    )
    db.add(foreign_org)
    db.flush()
    foreign_contract.organization_id = foreign_org.id
    db.add(foreign_contract)
    db.flush()
    foreign_risk = AnalysisRisk(
        organization_id=foreign_org.id,
        contract_id=foreign_contract.id,
        structured_result_id=result.id,
        title="不应跨组织可见",
        description="组织隔离测试",
        severity="critical",
        status="open",
        created_by=admin["id"],
    )
    db.add(foreign_risk)
    db.commit()
    risk_id = risk.id
    contract_id = contract.id
    db.close()

    summary = client.get("/api/v1/risks/summary", headers=headers)
    assert summary.status_code == 200, summary.text
    assert summary.json()["total"] == 1
    assert summary.json()["overdue"] == 1

    overdue = client.get("/api/v1/risks", params={"overdue_only": "true"}, headers=headers)
    assert overdue.status_code == 200, overdue.text
    assert overdue.json()["total"] == 1
    assert overdue.json()["items"][0]["contract_name"] == "阶段8合同"

    updated = client.patch(
        f"/api/v1/risks/{risk_id}",
        headers=headers,
        json={
            "status": "in_progress",
            "assignee_id": admin["id"],
            "remediation_due_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
            "remediation_notes": "业务确认付款节点并补充保障条款",
            "comment": "已分派法务跟进",
        },
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["status"] == "in_progress"
    assert updated.json()["assignee_id"] == admin["id"]
    assert updated.json()["is_overdue"] is False

    closed = client.patch(
        f"/api/v1/risks/{risk_id}",
        headers=headers,
        json={"status": "closed", "comment": "整改材料已复核归档"},
    )
    assert closed.status_code == 200, closed.text
    assert closed.json()["status"] == "closed"
    assert closed.json()["closed_by"] == admin["id"]
    assert closed.json()["closure_comment"] == "整改材料已复核归档"

    invalid = client.patch(
        f"/api/v1/risks/{risk_id}",
        headers=headers,
        json={"status": "accepted", "comment": "尝试非法回退"},
    )
    assert invalid.status_code == 409, invalid.text

    contract_risks = client.get(f"/api/v1/contracts/{contract_id}/risks", headers=headers)
    assert contract_risks.status_code == 200, contract_risks.text
    assert contract_risks.json()["summary"]["closed"] == 1

    db = local_session()
    assert db.query(AuditLog).filter(AuditLog.action == "risk.remediation_updated").count() == 2
    db.close()
    engine.dispose()
