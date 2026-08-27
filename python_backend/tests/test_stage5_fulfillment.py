"""Stage 5 contract detail, party, contact, task, and audit tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import config
import database
import main
from core import security
from models.contract import Base, Contract, FulfillmentTask, Organization, Party, User
from services import auth_service


def _settings(tmp_path: Path):
    data_dir = tmp_path / "data"
    return SimpleNamespace(
        environment="local",
        jwt_secret_key="stage5-test-secret",
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


def test_contract_detail_parties_contacts_and_task_state_machine(tmp_path: Path, monkeypatch):
    database_path = tmp_path / "stage5.db"
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
            "organization_name": "阶段5组织",
            "organization_code": "stage5",
            "username": "admin",
            "password": "stage5-password",
            "display_name": "阶段5管理员",
        },
    )
    assert bootstrap.status_code == 201, bootstrap.text
    headers = {"Authorization": f"Bearer {bootstrap.json()['access_token']}"}
    admin_user_id = bootstrap.json()["user"]["id"]

    contract = client.post(
        "/api/v1/contracts",
        headers=headers,
        json={"contract_no": "S5-001", "name": "履约测试合同", "status": "active"},
    ).json()
    contract_id = contract["id"]

    party = client.post(
        "/api/v1/parties",
        headers=headers,
        json={"name": "脱敏甲方有限公司", "party_type": "party_a", "tax_no": "TAX-001"},
    )
    assert party.status_code == 201, party.text
    party_id = party.json()["id"]
    linked = client.post(
        f"/api/v1/contracts/{contract_id}/parties",
        headers=headers,
        json={"party_id": party_id, "role": "party_a", "notes": "主合同甲方"},
    )
    assert linked.status_code == 201, linked.text
    contact = client.post(
        f"/api/v1/parties/{party_id}/contacts",
        headers=headers,
        json={"name": "李某", "title": "项目联系人", "phone": "010-00000000", "is_primary": True},
    )
    assert contact.status_code == 201, contact.text

    due_at = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    task = client.post(
        f"/api/v1/contracts/{contract_id}/tasks",
        headers=headers,
        json={
            "title": "提交验收资料",
            "task_type": "acceptance",
            "assignee_id": admin_user_id,
            "due_at": due_at,
            "remind_at": due_at,
        },
    )
    assert task.status_code == 201, task.text
    task_id = task.json()["id"]
    assert task.json()["status"] == "pending"
    assert task.json()["is_overdue"] is False

    started = client.patch(
        f"/api/v1/contracts/{contract_id}/tasks/{task_id}",
        headers=headers,
        json={"status": "in_progress"},
    )
    assert started.status_code == 200
    completed = client.patch(
        f"/api/v1/contracts/{contract_id}/tasks/{task_id}",
        headers=headers,
        json={"status": "completed"},
    )
    assert completed.status_code == 200
    assert completed.json()["completed_by"]
    completed_at = completed.json()["completed_at"]
    cleared_assignment = client.patch(
        f"/api/v1/contracts/{contract_id}/tasks/{task_id}",
        headers=headers,
        json={"description": "已完成归档", "assignee_id": None, "remind_at": None},
    )
    assert cleared_assignment.status_code == 200
    assert cleared_assignment.json()["assignee_id"] is None
    assert cleared_assignment.json()["remind_at"] is None
    assert cleared_assignment.json()["completed_at"] == completed_at
    invalid_transition = client.patch(
        f"/api/v1/contracts/{contract_id}/tasks/{task_id}",
        headers=headers,
        json={"status": "pending"},
    )
    assert invalid_transition.status_code == 409

    past_task = client.post(
        f"/api/v1/contracts/{contract_id}/tasks",
        headers=headers,
        json={"title": "无效任务", "due_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()},
    )
    assert past_task.status_code == 422

    viewer = client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "username": "stage5-viewer",
            "password": "stage5-viewer-password",
            "display_name": "阶段5只读用户",
            "roles": ["viewer"],
        },
    )
    assert viewer.status_code == 201
    viewer_login = client.post(
        "/api/v1/auth/login",
        json={"username": "stage5-viewer", "password": "stage5-viewer-password"},
    )
    viewer_headers = {"Authorization": f"Bearer {viewer_login.json()['access_token']}"}
    assert client.get(f"/api/v1/contracts/{contract_id}/detail", headers=viewer_headers).status_code == 200
    assignees = client.get("/api/v1/fulfillment-assignees", headers=viewer_headers)
    assert assignees.status_code == 200
    assert {item["display_name"] for item in assignees.json()} == {"阶段5管理员", "阶段5只读用户"}
    assert client.post(
        f"/api/v1/contracts/{contract_id}/tasks",
        headers=viewer_headers,
        json={"title": "禁止创建", "due_at": due_at},
    ).status_code == 403

    foreign_db = local_session()
    foreign_org = Organization(name="其他组织", code="stage5-foreign", metadata_json="{}")
    foreign_db.add(foreign_org)
    foreign_db.flush()
    foreign_user = User(
        organization_id=foreign_org.id,
        username="foreign-assignee",
        display_name="其他组织用户",
        status="active",
    )
    foreign_db.add(foreign_user)
    foreign_db.flush()
    foreign_contract = Contract(
        organization_id=foreign_org.id,
        contract_no="FOREIGN-001",
        name="其他组织合同",
        status="active",
        created_by=foreign_user.id,
        updated_by=foreign_user.id,
    )
    foreign_db.add(foreign_contract)
    foreign_db.commit()
    foreign_user_id = foreign_user.id
    foreign_contract_id = foreign_contract.id
    foreign_db.close()
    assert client.get(
        f"/api/v1/contracts/{foreign_contract_id}/detail", headers=headers
    ).status_code == 404
    assert client.get(
        f"/api/v1/contracts/{foreign_contract_id}/tasks", headers=headers
    ).status_code == 404
    assert client.post(
        f"/api/v1/contracts/{contract_id}/tasks",
        headers=headers,
        json={"title": "越权负责人", "assignee_id": foreign_user_id, "due_at": due_at},
    ).status_code == 422

    detail = client.get(f"/api/v1/contracts/{contract_id}/detail", headers=headers)
    assert detail.status_code == 200, detail.text
    payload = detail.json()
    assert payload["contract"]["id"] == contract_id
    assert payload["parties"][0]["party"]["name"] == "脱敏甲方有限公司"
    assert payload["parties"][0]["contacts"][0]["name"] == "李某"
    assert payload["tasks"][0]["status"] == "completed"
    assert any(item["action"] == "contract.task_created" for item in payload["operations"])
    assert any(item["action"] == "contact.created" for item in payload["operations"])

    deleted = client.delete(f"/api/v1/contracts/{contract_id}", headers=headers)
    assert deleted.status_code == 200
    assert client.get(f"/api/v1/contracts/{contract_id}/detail", headers=headers).status_code == 404
    assert client.get(f"/api/v1/contracts/{contract_id}/tasks", headers=headers).status_code == 404

    db = local_session()
    assert db.query(Contract).count() == 2
    assert db.query(Party).count() == 1
    assert db.query(FulfillmentTask).count() == 1
    db.close()
    engine.dispose()
