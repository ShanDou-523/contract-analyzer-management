"""Stage 10 durable job, provider delivery, and risk snapshot tests."""

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
    BackgroundJob,
    Base,
    Contract,
    ContractFile,
    FileVersion,
    NotificationDelivery,
    Organization,
    RiskReportSnapshot,
    StructuredAnalysisResult,
)
from models.document import AnalysisTemplate
from services import auth_service
from services.background_job_service import enqueue_job, recover_stale_jobs
from services.background_worker import (
    JOB_RISK_REMINDER_SCAN,
    JOB_RISK_SNAPSHOT,
    enqueue_pending_deliveries,
    process_one_job,
)


def _settings(tmp_path: Path):
    data_dir = tmp_path / "data"
    return SimpleNamespace(
        environment="local",
        jwt_secret_key="stage10-test-secret",
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


class FailingProvider:
    name = "failing"
    channel = "fake"

    def send(self, notification, recipient, *, idempotency_key):
        raise RuntimeError("deterministic delivery failure")


def test_stage10_migration_adds_durable_job_tables(tmp_path: Path):
    database_path = tmp_path / "migration.db"
    alembic_config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(Path(__file__).parents[1] / "alembic"))
    alembic_config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    command.upgrade(alembic_config, "head")
    engine = create_engine(f"sqlite:///{database_path}")
    inspector = inspect(engine)
    assert {"background_jobs", "notification_deliveries", "risk_report_snapshots"} <= set(
        inspector.get_table_names()
    )
    with engine.connect() as connection:
        assert (
            connection.execute(text("select version_num from alembic_version")).scalar_one()
            == "0010_background_jobs_snapshots"
        )
    engine.dispose()


def test_stage10_worker_retry_delivery_snapshots_and_scope(tmp_path: Path, monkeypatch):
    database_path = tmp_path / "stage10.db"
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
            "organization_name": "阶段10组织",
            "organization_code": "stage10",
            "username": "admin",
            "password": "stage10-password",
            "display_name": "阶段10管理员",
        },
    )
    assert bootstrap.status_code == 201, bootstrap.text
    admin = bootstrap.json()["user"]
    headers = {"Authorization": f"Bearer {bootstrap.json()['access_token']}"}
    test_now = datetime.now(timezone.utc)

    db = local_session()
    template = AnalysisTemplate(
        organization_id=admin["organization_id"],
        name="阶段10方案",
        fields_json="[]",
        version=1,
        is_default=True,
    )
    contract = Contract(
        organization_id=admin["organization_id"],
        name="阶段10合同",
        contract_no="S10-001",
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
        original_filename="stage10.pdf",
        storage_key="stage10.pdf",
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
        raw_json="{}",
        created_by=admin["id"],
    )
    db.add(result)
    db.flush()
    risk = AnalysisRisk(
        organization_id=admin["organization_id"],
        contract_id=contract.id,
        structured_result_id=result.id,
        title="阶段10逾期风险",
        description="验证持久任务",
        severity="critical",
        status="open",
        created_by=admin["id"],
        assignee_id=admin["id"],
        remediation_due_at=test_now - timedelta(hours=1),
    )
    db.add(risk)
    db.flush()
    risk_id = risk.id
    first_enqueue = enqueue_job(
        db,
        organization_id=admin["organization_id"],
        job_type=JOB_RISK_REMINDER_SCAN,
        dedupe_key="stage10-risk-scan",
        payload={"provider_name": "fake"},
        requested_by=admin["id"],
        available_at=test_now,
    )
    second_enqueue = enqueue_job(
        db,
        organization_id=admin["organization_id"],
        job_type=JOB_RISK_REMINDER_SCAN,
        dedupe_key="stage10-risk-scan",
        payload={"provider_name": "fake"},
        requested_by=admin["id"],
        available_at=test_now,
    )
    assert first_enqueue.created is True
    assert second_enqueue.created is False
    assert first_enqueue.job.id == second_enqueue.job.id
    stale = BackgroundJob(
        organization_id=admin["organization_id"],
        job_type="stale-test",
        status="running",
        priority=-10,
        payload_json="{}",
        result_json="{}",
        dedupe_key="stage10-stale",
        attempts=1,
        max_attempts=3,
        available_at=test_now,
        locked_at=test_now - timedelta(minutes=10),
    )
    db.add(stale)
    db.commit()
    assert recover_stale_jobs(db, now=test_now, lock_timeout_seconds=60) == 1
    assert stale.status == "queued"
    stale.status = "cancelled"
    db.commit()
    db.close()

    scan_job = process_one_job(local_session, now=test_now, worker_id="stage10-worker")
    assert scan_job and scan_job.status == "succeeded"
    delivery_job = process_one_job(
        local_session,
        now=test_now + timedelta(seconds=1),
        worker_id="stage10-worker",
    )
    assert delivery_job and delivery_job.status == "succeeded"

    db = local_session()
    persisted_risk = db.get(AnalysisRisk, risk_id)
    assert persisted_risk.status == "open"
    fake_delivery = db.query(NotificationDelivery).filter_by(provider_name="fake").one()
    assert fake_delivery.status == "sent"
    assert fake_delivery.provider_message_id.startswith("fake-")

    snapshot_job = enqueue_job(
        db,
        organization_id=admin["organization_id"],
        job_type=JOB_RISK_SNAPSHOT,
        dedupe_key="stage10-snapshot",
        payload={"snapshot_date": test_now.date().isoformat()},
        requested_by=admin["id"],
        available_at=test_now,
    ).job
    db.commit()
    snapshot_job_id = snapshot_job.id
    db.close()
    completed_snapshot = process_one_job(
        local_session,
        now=test_now + timedelta(seconds=2),
        worker_id="stage10-worker",
    )
    assert completed_snapshot and completed_snapshot.id == snapshot_job_id
    assert completed_snapshot.status == "succeeded"

    db = local_session()
    snapshot = db.query(RiskReportSnapshot).filter_by(organization_id=admin["organization_id"]).one()
    assert snapshot.total == 1
    assert snapshot.overdue == 1
    assert float(snapshot.overdue_rate) == 100
    assert enqueue_pending_deliveries(
        db,
        admin["organization_id"],
        provider_name="failing",
        requested_by=admin["id"],
    ) == 1
    db.commit()
    db.close()

    failing_registry = {"failing": FailingProvider()}
    failed_job = None
    for seconds in (3, 10, 30):
        failed_job = process_one_job(
            local_session,
            providers=failing_registry,
            now=test_now + timedelta(seconds=seconds),
            worker_id="stage10-failing-worker",
        )
    assert failed_job and failed_job.status == "failed"
    db = local_session()
    failed_delivery = db.query(NotificationDelivery).filter_by(provider_name="failing").one()
    assert failed_delivery.status == "failed"
    assert failed_delivery.attempt_count == 3
    assert db.get(AnalysisRisk, risk_id).status == "open"

    foreign_org = Organization(name="阶段10其他组织", code="stage10-other")
    db.add(foreign_org)
    db.flush()
    db.add(
        RiskReportSnapshot(
            organization_id=foreign_org.id,
            snapshot_date=test_now.date(),
            total=99,
            active=99,
            overdue=99,
            closed=0,
            critical=99,
            overdue_rate=100,
            contract_rankings_json="[]",
            assignee_workloads_json="[]",
            generated_at=test_now,
        )
    )
    db.commit()
    failed_job_id = failed_job.id
    db.close()

    jobs = client.get("/api/v1/background-jobs", headers=headers)
    assert jobs.status_code == 200, jobs.text
    assert jobs.json()["total"] >= 4
    assert all(item["organization_id"] == admin["organization_id"] for item in jobs.json()["items"])
    deliveries = client.get("/api/v1/notification-deliveries", headers=headers)
    assert deliveries.status_code == 200
    assert deliveries.json()["total"] == 2
    snapshots = client.get("/api/v1/risk-reports/snapshots", headers=headers)
    assert snapshots.status_code == 200
    assert snapshots.json()["total"] == 1
    assert snapshots.json()["items"][0]["overdue_rate"] == 100
    exported = client.get("/api/v1/risk-reports/snapshots/export", headers=headers)
    assert exported.status_code == 200
    assert test_now.date().isoformat() in exported.content.decode("utf-8-sig")
    retried = client.post(f"/api/v1/background-jobs/{failed_job_id}/retry", headers=headers)
    assert retried.status_code == 200, retried.text
    assert retried.json()["status"] == "queued"
    assert retried.json()["attempts"] == 0
    engine.dispose()
