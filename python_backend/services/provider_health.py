"""Lightweight dependency checks for readiness diagnostics."""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import text

from config import settings


def check_database(engine) -> dict:
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ok", "detail": "database reachable"}
    except Exception as exc:  # pragma: no cover - environment-specific failure
        return {"status": "error", "detail": type(exc).__name__}


def check_redis() -> dict:
    if not settings.redis_url:
        return {"status": "not_configured", "detail": "CONTRACT_ANALYZER_REDIS_URL is empty"}
    try:
        import redis

        redis.Redis.from_url(settings.redis_url).ping()
        return {"status": "ok", "detail": "redis reachable"}
    except Exception as exc:  # pragma: no cover - optional dependency/network
        return {"status": "error", "detail": type(exc).__name__}


def check_storage() -> dict:
    """Check that the configured local storage directory is available."""
    path = Path(settings.resolved_upload_dir)
    if path.is_dir():
        return {"status": "ok", "detail": "local upload directory reachable"}
    return {"status": "error", "detail": "upload directory is missing"}


def _configured_secret(key: str, env_name: str) -> bool:
    from database import SessionLocal
    from services.secret_service import get_secret_setting

    try:
        db = SessionLocal()
        try:
            return bool(get_secret_setting(db, key) or os.getenv(env_name, ""))
        finally:
            db.close()
    except Exception:  # pragma: no cover - database may not be initialized yet
        return bool(os.getenv(env_name, ""))


def check_ocr() -> dict:
    if _configured_secret("baidu_ocr_api_key", "BAIDU_OCR_API_KEY") and _configured_secret(
        "baidu_ocr_secret_key", "BAIDU_OCR_SECRET_KEY"
    ):
        return {"status": "configured", "detail": "Baidu OCR credentials available"}
    return {"status": "not_configured", "detail": "Baidu OCR credentials are missing"}


def check_ai() -> dict:
    if _configured_secret("deepseek_api_key", "DEEPSEEK_API_KEY"):
        return {"status": "configured", "detail": "DeepSeek credentials available"}
    return {"status": "not_configured", "detail": "DeepSeek API key is missing"}
