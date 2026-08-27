"""Stage 6 reminder, notification, task-query, and dashboard tests."""

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
    Base,
    Contract,
    FulfillmentTask,
    Notification,
    Organization,
    User,
)
from services import auth_service, fulfillment_service, notification_service


def _settings(tmp_path: Path):
    data_dir = tmp_path / "data"
    return SimpleNamespace(
        environment="local",
        jwt_secret_key="stage6-test-secret",
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


def test_stage6_migration_adds_notification_table(tmp_path: Path):
    database_path = tmp_path / "migration.db"
    alembic_config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    alembic_config.set_main_option(
        "script_location",
        str(Path(__file__).parents[1] / "alembic"),
    )
    alembic_config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")

    command.upgrade(alembic_config, "head")

    engine = create_engine(f"sqlite:///{database_path}")
    inspector = inspect(engine)
    assert "notifications" in inspector.get_table_names()
    assert {
        "organization_id",
        "recipient_id",
        "contract_id",
        "task_id",
        "notification_type",
        "status",
        "dedupe_key",
    } <= {column["name"] for column in inspector.get_columns("notifications")}
    engine.dispose()


def test_reminder_scan_notifications_dashboard_and_organization_scope(
    tmp_path: Path,
    monkeypatch,
):
    database_path = tmp_path / "stage6.db"
    engine = create_engine(f"sqlite:///{database_path}")
    Base.metadata.create_all(engine)
    local_session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    test_settings = _settings(tmp_path)
    monkeypatch.setattr(database, "SessionLocal", local_session)
    monkeypatch.setattr(database, "DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setattr(security, "settings", test_settings)
    monkeypatch.setattr(auth_service, "settings", test_settings)
    monkeypatch.setattr(config, "settings", test_settings)

    creation_now = datetime(2026, 6, 1, 8, tzinfo=timezone.utc)
    scan_now = datetime(2026, 6, 15, 8, tzinfo=timezone.utc)
    monkeypatch.setattr(fulfillment_service, "now_utc", lambda: creation_now)
    monkeypatch.setattr(notification_service, "now_utc", lambda: scan_now)

    client = TestClient(main.app)
    bootstrap = client.post(
        "/api/v1/auth/bootstrap",
        json={
            "organization_name": "阶段6组织",
            "organization_code": "stage6",
            "username": "admin",
            "password": "stage6-password",
            "display_name": "阶段6管理员",
        },
    )
    assert bootstrap.status_code == 201, bootstrap.text
    headers = {"Authorization": f"Bearer {bootstrap.json()['access_token']}"}
    admin_user_id = bootstrap.json()["user"]["id"]
    contract = client.post(
        "/api/v1/contracts",
        headers=headers,
        json={"contract_no": "S6-001", "name": "履约提醒测试合同", "status": "active"},
    )
    contract_id = contract.json()["id"]

    tasks = [
        {
            "title": "提交验收材料",
            "priority": "critical",
            "assignee_id": admin_user_id,
            "due_at": (scan_now - timedelta(days=1)).isoformat(),
            "remind_at": (scan_now - timedelta(days=2)).isoformat(),
        },
        {
            "title": "准备付款凭证",
            "priority": "high",
            "assignee_id": admin_user_id,
            "due_at": (scan_now + timedelta(days=3)).isoformat(),
            "remind_at": (scan_now - timedelta(days=1)).isoformat(),
        },
        {
            "title": "补充归档文件",
            "priority": "medium",
            "due_at": (scan_now - timedelta(hours=1)).isoformat(),
        },
    ]
    task_ids = []
    for payload in tasks:
        response = client.post(
            f"/api/v1/contracts/{contract_id}/tasks",
            headers=headers,
            json=payload,
        )
        assert response.status_code == 201, response.text
        task_ids.append(response.json()["id"])

    monkeypatch.setattr(fulfillment_service, "now_utc", lambda: scan_now)
    first_scan = client.post("/api/v1/fulfillment/reminders/scan", headers=headers)
    assert first_scan.status_code == 200, first_scan.text
    assert first_scan.json() == {
        "examined_tasks": 3,
        "created": 4,
        "skipped_existing": 0,
        "skipped_without_recipient": 0,
    }
    second_scan = client.post("/api/v1/fulfillment/reminders/scan", headers=headers)
    assert second_scan.status_code == 200
    assert second_scan.json()["created"] == 0
    assert second_scan.json()["skipped_existing"] == 4

    task_search = client.get(
        "/api/v1/fulfillment/tasks",
        headers=headers,
        params={"search": "验收", "overdue_only": True},
    )
    assert task_search.status_code == 200, task_search.text
    assert task_search.json()["total"] == 1
    assert task_search.json()["items"][0]["contract_name"] == "履约提醒测试合同"
    assert task_search.json()["items"][0]["is_overdue"] is True
    unassigned = client.get(
        "/api/v1/fulfillment/tasks",
        headers=headers,
        params={"assignee_id": "unassigned"},
    )
    assert unassigned.json()["total"] == 1

    dashboard = client.get("/api/v1/fulfillment/dashboard", headers=headers)
    assert dashboard.status_code == 200, dashboard.text
    summary = dashboard.json()
    assert summary["total_open"] == 3
    assert summary["pending"] == 3
    assert summary["overdue"] == 2
    assert summary["due_next_7_days"] == 1
    assert summary["unassigned"] == 1
    assert summary["unread_notifications"] == 4

    notifications = client.get("/api/v1/notifications", headers=headers)
    assert notifications.status_code == 200
    assert notifications.json()["total"] == 4
    assert notifications.json()["unread"] == 4
    assert (
        client.get(
            "/api/v1/notifications",
            headers=headers,
            params={"notification_type": "overdue"},
        ).json()["total"]
        == 2
    )

    first_id, second_id = [item["id"] for item in notifications.json()["items"][:2]]
    marked_read = client.patch(
        f"/api/v1/notifications/{first_id}",
        headers=headers,
        json={"status": "read"},
    )
    assert marked_read.status_code == 200
    assert marked_read.json()["read_at"] is not None
    ignored = client.patch(
        f"/api/v1/notifications/{second_id}",
        headers=headers,
        json={"status": "ignored"},
    )
    assert ignored.status_code == 200
    assert ignored.json()["ignored_at"] is not None
    assert client.get("/api/v1/notifications/unread-count", headers=headers).json()["count"] == 2
    marked_all = client.post("/api/v1/notifications/read-all", headers=headers)
    assert marked_all.json()["updated"] == 2
    assert client.get("/api/v1/notifications/unread-count", headers=headers).json()["count"] == 0

    viewer = client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "username": "stage6-viewer",
            "password": "stage6-viewer-password",
            "display_name": "阶段6只读用户",
            "roles": ["viewer"],
        },
    )
    assert viewer.status_code == 201
    viewer_login = client.post(
        "/api/v1/auth/login",
        json={"username": "stage6-viewer", "password": "stage6-viewer-password"},
    )
    viewer_headers = {"Authorization": f"Bearer {viewer_login.json()['access_token']}"}
    assert (
        client.post(
            "/api/v1/fulfillment/reminders/scan",
            headers=viewer_headers,
        ).status_code
        == 403
    )
    assert client.get("/api/v1/notifications", headers=viewer_headers).json()["total"] == 0
    assert (
        client.get("/api/v1/fulfillment/dashboard", headers=viewer_headers).json()["total_open"]
        == 3
    )

    foreign_db = local_session()
    foreign_org = Organization(name="其他组织", code="stage6-foreign", metadata_json="{}")
    foreign_db.add(foreign_org)
    foreign_db.flush()
    foreign_user = User(
        organization_id=foreign_org.id,
        username="stage6-foreign-user",
        display_name="其他组织用户",
        status="active",
    )
    foreign_db.add(foreign_user)
    foreign_db.flush()
    foreign_contract = Contract(
        organization_id=foreign_org.id,
        contract_no="FOREIGN-S6",
        name="其他组织履约合同",
        status="active",
        created_by=foreign_user.id,
        updated_by=foreign_user.id,
    )
    foreign_db.add(foreign_contract)
    foreign_db.flush()
    foreign_task = FulfillmentTask(
        organization_id=foreign_org.id,
        contract_id=foreign_contract.id,
        title="其他组织任务",
        status="pending",
        priority="medium",
        due_at=scan_now - timedelta(days=1),
        created_by=foreign_user.id,
        updated_by=foreign_user.id,
    )
    foreign_db.add(foreign_task)
    foreign_db.flush()
    foreign_notification = Notification(
        organization_id=foreign_org.id,
        recipient_id=foreign_user.id,
        contract_id=foreign_contract.id,
        task_id=foreign_task.id,
        notification_type="overdue",
        status="unread",
        title="其他组织通知",
        message="脱敏内容",
        source_at=foreign_task.due_at,
        dedupe_key="foreign-stage6-notification",
        generated_at=scan_now,
    )
    foreign_db.add(foreign_notification)
    foreign_db.commit()
    foreign_notification_id = foreign_notification.id
    foreign_db.close()

    assert (
        client.patch(
            f"/api/v1/notifications/{foreign_notification_id}",
            headers=headers,
            json={"status": "read"},
        ).status_code
        == 404
    )
    assert client.get("/api/v1/fulfillment/tasks", headers=headers).json()["total"] == 3

    assert client.delete(f"/api/v1/contracts/{contract_id}", headers=headers).status_code == 200
    assert client.get("/api/v1/fulfillment/tasks", headers=headers).json()["total"] == 0
    assert client.get("/api/v1/notifications", headers=headers).json()["total"] == 0
    assert client.get("/api/v1/fulfillment/dashboard", headers=headers).json()["total_open"] == 0
    assert (
        client.post("/api/v1/fulfillment/reminders/scan", headers=headers).json()["examined_tasks"]
        == 0
    )

    db = local_session()
    assert db.query(FulfillmentTask).count() == 4
    assert db.query(Notification).count() == 5
    db.close()
    engine.dispose()
