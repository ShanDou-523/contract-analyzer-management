"""Authentication endpoints for the v1 API."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from config import settings
from core.security import (
    CurrentPrincipal,
    as_utc,
    create_access_token,
    find_refresh_session,
    get_current_principal,
    hash_password,
    issue_refresh_token,
    utcnow,
    verify_password,
)
from database import get_db
from models.contract import Organization, User, UserRole
from models.document import AnalysisTemplate
from schemas.auth import (
    BootstrapRequest,
    LoginRequest,
    PasswordChange,
    RefreshRequest,
    TokenResponse,
    UserOut,
)
from services.audit_service import record_audit
from services.auth_service import assign_roles, ensure_roles

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        email=user.email,
        organization_id=user.organization_id,
        status=user.status,
        roles=sorted({assignment.role.name for assignment in user.roles if assignment.role}),
    )


def _tokens(db: Session, user: User) -> TokenResponse:
    access_token, expires_at = create_access_token(user)
    refresh_token, _ = issue_refresh_token(db, user)
    db.commit()
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at,
        user=_user_out(user),
    )


@router.post("/bootstrap", response_model=TokenResponse, status_code=201)
def bootstrap(data: BootstrapRequest, db: Session = Depends(get_db)):
    """Create the first administrator; disabled after the first user exists."""
    existing_users = db.query(User).order_by(User.created_at.asc()).all()
    legacy_recovery_mode = bool(existing_users) and all(
        not user.password_hash for user in existing_users
    )
    if existing_users and not legacy_recovery_mode:
        raise HTTPException(status_code=409, detail="系统已完成初始化")
    if settings.environment == "production":
        raise HTTPException(status_code=403, detail="生产环境不允许通过公开接口初始化")
    if (
        not legacy_recovery_mode
        and db.query(Organization).filter(Organization.code == data.organization_code).first()
    ):
        raise HTTPException(status_code=409, detail="组织编码已存在")

    organization = (
        db.query(Organization).order_by(Organization.created_at.asc()).first()
        if legacy_recovery_mode
        else Organization(
            name=data.organization_name,
            code=data.organization_code,
            status="active",
            metadata_json="{}",
        )
    )
    if organization not in db.query(Organization).all():
        db.add(organization)
        db.flush()
    db.query(AnalysisTemplate).filter(AnalysisTemplate.organization_id.is_(None)).update(
        {AnalysisTemplate.organization_id: organization.id}, synchronize_session=False
    )
    roles = ensure_roles(db, organization)
    user = User(
        organization_id=organization.id,
        username=data.username,
        display_name=data.display_name,
        password_hash=hash_password(data.password),
        status="active",
    )
    db.add(user)
    db.flush()
    user.roles.append(UserRole(role_id=roles["system_admin"].id))
    record_audit(
        db,
        "auth.bootstrap",
        organization_id=organization.id,
        user_id=user.id,
        resource_type="organization",
        resource_id=organization.id,
    )
    return _tokens(db, user)


@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == data.username).one_or_none()
    now = utcnow()
    if user and as_utc(user.locked_until) and as_utc(user.locked_until) > now:
        raise HTTPException(status_code=429, detail="登录失败次数过多，请稍后重试")
    if (
        user is None
        or not verify_password(data.password, user.password_hash)
        or user.status != "active"
    ):
        if user:
            user.failed_login_count += 1
            if user.failed_login_count >= settings.max_login_attempts:
                user.locked_until = now + timedelta(minutes=settings.lockout_minutes)
                user.failed_login_count = 0
            record_audit(
                db,
                "auth.login_failed",
                organization_id=user.organization_id,
                user_id=user.id,
            )
            db.commit()
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    record_audit(db, "auth.login", organization_id=user.organization_id, user_id=user.id)
    return _tokens(db, user)


@router.post("/refresh", response_model=TokenResponse)
def refresh(data: RefreshRequest, db: Session = Depends(get_db)):
    session = find_refresh_session(db, data.refresh_token)
    if session is None:
        raise HTTPException(status_code=401, detail="刷新令牌无效或已过期")
    user = db.get(User, session.user_id)
    if user is None or user.status != "active":
        raise HTTPException(status_code=401, detail="用户不存在或已停用")
    session.revoked_at = utcnow()
    session.last_used_at = utcnow()
    record_audit(db, "auth.refresh", organization_id=user.organization_id, user_id=user.id)
    return _tokens(db, user)


@router.post("/logout")
def logout(
    data: RefreshRequest,
    principal: CurrentPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    session = find_refresh_session(db, data.refresh_token)
    if session and session.user_id == principal.user_id:
        session.revoked_at = utcnow()
        record_audit(
            db, "auth.logout", organization_id=principal.organization_id, user_id=principal.user_id
        )
        db.commit()
    return {"message": "已退出登录"}


@router.get("/me", response_model=UserOut)
def me(principal: CurrentPrincipal = Depends(get_current_principal)):
    return _user_out(principal.user)


@router.post("/password")
def change_password(
    data: PasswordChange,
    principal: CurrentPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    principal.user.password_hash = hash_password(data.password)
    record_audit(
        db,
        "auth.password_changed",
        organization_id=principal.organization_id,
        user_id=principal.user_id,
    )
    db.commit()
    return {"message": "密码已更新"}
