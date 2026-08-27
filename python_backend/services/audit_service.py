"""Audit-log persistence without recording sensitive request bodies."""

from __future__ import annotations

import json

from sqlalchemy.orm import Session

from core.logging import request_id_var
from models.contract import AuditLog


def record_audit(
    db: Session,
    action: str,
    *,
    organization_id: str | None = None,
    user_id: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    details: dict | None = None,
) -> AuditLog:
    entry = AuditLog(
        organization_id=organization_id,
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details_json=json.dumps(details or {}, ensure_ascii=False),
        request_id=request_id_var.get(),
    )
    db.add(entry)
    return entry
