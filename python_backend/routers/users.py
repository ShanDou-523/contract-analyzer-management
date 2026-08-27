"""Organization user and role administration endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from core.security import CurrentPrincipal, get_current_principal, hash_password, require_roles
from database import get_db
from models.contract import Role, User, UserRole
from schemas.auth import RoleOut, UserCreate, UserOut, UserUpdate
from services.audit_service import record_audit
from services.auth_service import assign_roles

router = APIRouter(prefix="/api/v1", tags=["users"])


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


@router.get("/roles", response_model=list[RoleOut])
def list_roles(
    principal: CurrentPrincipal = Depends(get_current_principal),
    db: Session = Depends(get_db),
):
    return (
        db.query(Role)
        .filter(Role.organization_id == principal.organization_id)
        .order_by(Role.name)
        .all()
    )


@router.get("/users", response_model=list[UserOut])
def list_users(
    principal: CurrentPrincipal = Depends(require_roles("system_admin", "org_admin")),
    db: Session = Depends(get_db),
):
    users = (
        db.query(User)
        .filter(User.organization_id == principal.organization_id)
        .order_by(User.created_at.asc())
        .all()
    )
    return [_user_out(user) for user in users]


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(
    data: UserCreate,
    principal: CurrentPrincipal = Depends(require_roles("system_admin", "org_admin")),
    db: Session = Depends(get_db),
):
    if db.query(User).filter(User.username == data.username).first():
        raise HTTPException(status_code=409, detail="用户名已存在")
    if "system_admin" in data.roles and "system_admin" not in principal.roles:
        raise HTTPException(status_code=403, detail="只有系统管理员可以授予 system_admin")
    user = User(
        organization_id=principal.organization_id,
        username=data.username,
        display_name=data.display_name,
        email=data.email,
        password_hash=hash_password(data.password),
        status="active",
    )
    db.add(user)
    db.flush()
    try:
        assign_roles(db, user, data.roles)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record_audit(
        db,
        "user.created",
        organization_id=principal.organization_id,
        user_id=principal.user_id,
        resource_type="user",
        resource_id=user.id,
        details={"username": user.username, "roles": data.roles},
    )
    db.commit()
    db.refresh(user)
    return _user_out(user)


@router.put("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: str,
    data: UserUpdate,
    principal: CurrentPrincipal = Depends(require_roles("system_admin", "org_admin")),
    db: Session = Depends(get_db),
):
    user = (
        db.query(User)
        .filter(User.id == user_id, User.organization_id == principal.organization_id)
        .one_or_none()
    )
    if user is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    if data.roles is not None:
        if "system_admin" in data.roles and "system_admin" not in principal.roles:
            raise HTTPException(status_code=403, detail="只有系统管理员可以授予 system_admin")
        try:
            assign_roles(db, user, data.roles)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    if data.display_name is not None:
        user.display_name = data.display_name
    if data.email is not None:
        user.email = data.email
    if data.status is not None:
        user.status = data.status
    if data.password:
        user.password_hash = hash_password(data.password)
    record_audit(
        db,
        "user.updated",
        organization_id=principal.organization_id,
        user_id=principal.user_id,
        resource_type="user",
        resource_id=user.id,
        details={"fields": list(data.model_dump(exclude_none=True).keys())},
    )
    db.commit()
    db.refresh(user)
    return _user_out(user)
