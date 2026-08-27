"""Stage 3 authentication, authorization, and organization isolation tests."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import config
import database
import main
from core import security
from models.contract import AuditLog, Base, Contract, Organization, User
from services import auth_service


def _test_settings(tmp_path: Path):
    return SimpleNamespace(
        environment="local",
        jwt_secret_key="stage3-test-secret",
        jwt_secret_key_path=tmp_path / "jwt.key",
        access_token_expire_minutes=30,
        refresh_token_expire_days=14,
        max_login_attempts=3,
        lockout_minutes=15,
        admin_username="",
        admin_password="",
    )


def test_bootstrap_login_role_guard_and_contract_scope(tmp_path: Path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'auth.db'}")
    Base.metadata.create_all(engine)
    local_session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    test_settings = _test_settings(tmp_path)
    monkeypatch.setattr(database, "SessionLocal", local_session)
    monkeypatch.setattr(security, "settings", test_settings)
    monkeypatch.setattr(auth_service, "settings", test_settings)
    monkeypatch.setattr(config, "settings", test_settings)

    client = TestClient(main.app)
    bootstrap = client.post(
        "/api/v1/auth/bootstrap",
        json={
            "organization_name": "测试组织",
            "organization_code": "stage3",
            "username": "admin",
            "password": "stage3-password",
            "display_name": "测试管理员",
        },
    )
    assert bootstrap.status_code == 201, bootstrap.text
    tokens = bootstrap.json()
    assert tokens["user"]["roles"] == ["system_admin"]
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    assert client.get("/api/v1/auth/me", headers=headers).json()["username"] == "admin"
    created = client.post(
        "/api/v1/contracts",
        headers=headers,
        json={"contract_no": "S3-001", "name": "阶段3合同", "amount": "100.00"},
    )
    assert created.status_code == 201, created.text
    listed = client.get("/api/v1/contracts", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    unauthenticated = client.get("/api/v1/contracts")
    assert unauthenticated.status_code == 401
    assert unauthenticated.json()["message"] == "请先登录"

    bad_login = client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "wrong-password"}
    )
    assert bad_login.status_code == 401
    assert bad_login.json()["message"] == "用户名或密码错误"

    viewer = client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "username": "viewer",
            "password": "viewer-password",
            "display_name": "只读用户",
            "roles": ["viewer"],
        },
    )
    assert viewer.status_code == 201, viewer.text
    viewer_login = client.post(
        "/api/v1/auth/login", json={"username": "viewer", "password": "viewer-password"}
    )
    viewer_headers = {"Authorization": f"Bearer {viewer_login.json()['access_token']}"}
    forbidden = client.post(
        "/api/v1/contracts",
        headers=viewer_headers,
        json={"name": "不应创建"},
    )
    assert forbidden.status_code == 403

    viewer_contracts = client.get("/api/v1/contracts", headers=viewer_headers)
    assert viewer_contracts.status_code == 200
    assert viewer_contracts.json()["total"] == 1

    rotated = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert rotated.status_code == 200, rotated.text
    rotated_tokens = rotated.json()
    assert rotated_tokens["refresh_token"] != tokens["refresh_token"]
    reused = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert reused.status_code == 401

    logout = client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {rotated_tokens['access_token']}"},
        json={"refresh_token": rotated_tokens["refresh_token"]},
    )
    assert logout.status_code == 200
    revoked = client.post(
        "/api/v1/auth/refresh", json={"refresh_token": rotated_tokens["refresh_token"]}
    )
    assert revoked.status_code == 401

    db = local_session()
    assert db.query(Organization).count() == 1
    assert db.query(User).count() == 2
    assert db.query(Contract).count() == 1
    assert db.query(AuditLog).filter(AuditLog.action == "contract.created").count() == 1
    db.close()
    engine.dispose()
