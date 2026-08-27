"""Authentication bootstrap, role seeding, and user management helpers."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from config import settings
from core.security import hash_password
from models.contract import Organization, Role, User, UserRole
from models.document import AnalysisTemplate

ROLE_DEFINITIONS = {
    "system_admin": "系统、组织、供应商和权限配置",
    "org_admin": "本组织用户、部门、分类和模板管理",
    "contract_manager": "合同创建、文件、分析和履约台账",
    "reviewer": "复核、审批和结构化结果修改",
    "viewer": "按权限查看合同和报表",
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def ensure_roles(db: Session, organization: Organization) -> dict[str, Role]:
    roles: dict[str, Role] = {}
    for name, description in ROLE_DEFINITIONS.items():
        role = (
            db.query(Role)
            .filter(Role.organization_id == organization.id, Role.name == name)
            .one_or_none()
        )
        if role is None:
            role = Role(
                id=str(uuid.uuid5(uuid.UUID(organization.id), f"role:{name}")),
                organization_id=organization.id,
                name=name,
                description=description,
            )
            db.add(role)
            db.flush()
        roles[name] = role
    return roles


def ensure_auth_baseline(db: Session) -> User | None:
    """Seed roles and optionally create the configured first administrator."""
    organizations = db.query(Organization).order_by(Organization.created_at.asc()).all()
    for organization in organizations:
        ensure_roles(db, organization)

    if not settings.admin_username or not settings.admin_password:
        db.commit()
        return None
    if len(settings.admin_password) < 10:
        raise ValueError("CONTRACT_ANALYZER_ADMIN_PASSWORD 至少需要 10 个字符")

    organization = (
        organizations[0]
        if organizations
        else Organization(
            id=str(uuid.uuid4()),
            name="默认组织",
            code="default",
            status="active",
            metadata_json="{}",
        )
    )
    if organization not in organizations:
        db.add(organization)
        db.flush()
    roles = ensure_roles(db, organization)
    db.query(AnalysisTemplate).filter(AnalysisTemplate.organization_id.is_(None)).update(
        {AnalysisTemplate.organization_id: organization.id}, synchronize_session=False
    )
    user = db.query(User).filter(User.username == settings.admin_username).one_or_none()
    if user is None:
        user = User(
            id=str(uuid.uuid4()),
            organization_id=organization.id,
            username=settings.admin_username,
            display_name=settings.admin_username,
            password_hash=hash_password(settings.admin_password),
            status="active",
        )
        db.add(user)
        db.flush()
    elif not user.password_hash:
        user.password_hash = hash_password(settings.admin_password)
        user.status = "active"

    if not any(item.role and item.role.name == "system_admin" for item in user.roles):
        db.add(UserRole(user_id=user.id, role_id=roles["system_admin"].id))
    db.commit()
    return user


def assign_roles(db: Session, user: User, role_names: list[str]) -> None:
    requested = set(role_names or ["viewer"])
    invalid = requested.difference(ROLE_DEFINITIONS)
    if invalid:
        raise ValueError(f"未知角色: {', '.join(sorted(invalid))}")
    roles = {
        role.name: role
        for role in db.query(Role)
        .filter(Role.organization_id == user.organization_id, Role.name.in_(requested))
        .all()
    }
    if len(roles) != len(requested):
        raise ValueError("用户角色尚未初始化")
    user.roles.clear()
    db.flush()
    for role in roles.values():
        user.roles.append(UserRole(role_id=role.id))
