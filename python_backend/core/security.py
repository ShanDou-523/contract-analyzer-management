"""Password hashing, access tokens, refresh sessions, and auth dependencies."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from config import settings
from core.logging import organization_id_var, user_id_var
from database import get_db
from models.contract import AuthSession, User

PASSWORD_PREFIX = "scrypt-v1"
bearer_scheme = HTTPBearer(auto_error=False)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )


def hash_password(password: str) -> str:
    if len(password) < 10:
        raise ValueError("密码至少需要 10 个字符")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=64)
    return ":".join(
        [
            PASSWORD_PREFIX,
            base64.urlsafe_b64encode(salt).decode("ascii"),
            base64.urlsafe_b64encode(digest).decode("ascii"),
        ]
    )


def verify_password(password: str, encoded: str | None) -> bool:
    if not encoded:
        return False
    try:
        prefix, salt_text, digest_text = encoded.split(":", 2)
        if prefix != PASSWORD_PREFIX:
            return False
        salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_text.encode("ascii"))
        actual = hashlib.scrypt(
            password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=len(expected)
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def _jwt_secret() -> str:
    if settings.jwt_secret_key.strip():
        return settings.jwt_secret_key.strip()
    path = settings.jwt_secret_key_path
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return path.read_text(encoding="ascii").strip()
    value = secrets.token_urlsafe(48)
    path.write_text(value, encoding="ascii")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return value


def role_names(user: User) -> list[str]:
    return sorted({assignment.role.name for assignment in user.roles if assignment.role})


def create_access_token(user: User) -> tuple[str, datetime]:
    expires_at = utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {
        "sub": user.id,
        "organization_id": user.organization_id,
        "roles": role_names(user),
        "type": "access",
        "jti": str(uuid.uuid4()),
        "iat": utcnow(),
        "exp": expires_at,
    }
    return jwt.encode(payload, _jwt_secret(), algorithm="HS256"), expires_at


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, _jwt_secret(), algorithms=["HS256"])
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="登录已过期，请重新登录") from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="无效的访问令牌") from exc
    if payload.get("type") != "access" or not payload.get("sub"):
        raise HTTPException(status_code=401, detail="无效的访问令牌")
    return payload


def issue_refresh_token(db: Session, user: User) -> tuple[str, AuthSession]:
    token = secrets.token_urlsafe(48)
    session = AuthSession(
        user_id=user.id,
        organization_id=user.organization_id,
        refresh_token_hash=hashlib.sha256(token.encode("utf-8")).hexdigest(),
        expires_at=utcnow() + timedelta(days=settings.refresh_token_expire_days),
    )
    db.add(session)
    db.flush()
    return token, session


def find_refresh_session(db: Session, token: str) -> AuthSession | None:
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    session = db.query(AuthSession).filter(AuthSession.refresh_token_hash == digest).one_or_none()
    if session is None or session.revoked_at is not None:
        return None
    if as_utc(session.expires_at) <= utcnow():
        return None
    return session


@dataclass(frozen=True)
class CurrentPrincipal:
    user: User
    roles: frozenset[str]

    @property
    def user_id(self) -> str:
        return self.user.id

    @property
    def organization_id(self) -> str:
        return self.user.organization_id


def get_current_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> CurrentPrincipal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="请先登录")
    payload = decode_access_token(credentials.credentials)
    user = db.get(User, payload["sub"])
    if user is None or user.status != "active":
        raise HTTPException(status_code=401, detail="用户不存在或已停用")
    if user.organization_id != payload.get("organization_id"):
        raise HTTPException(status_code=401, detail="组织上下文已失效")
    principal = CurrentPrincipal(user=user, roles=frozenset(role_names(user)))
    user_id_var.set(user.id)
    organization_id_var.set(user.organization_id)
    return principal


def require_roles(*allowed_roles: str):
    allowed = frozenset(allowed_roles)

    def dependency(
        principal: CurrentPrincipal = Depends(get_current_principal),
    ) -> CurrentPrincipal:
        if allowed and not principal.roles.intersection(allowed):
            raise HTTPException(status_code=403, detail="没有执行此操作的权限")
        return principal

    return dependency
