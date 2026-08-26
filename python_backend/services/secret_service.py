"""Encrypted-at-rest application secrets with legacy plaintext compatibility."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from config import settings

logger = logging.getLogger("contract_analyzer.secrets")
PREFIX = "enc:v1:"


def _key_file() -> Path:
    settings.resolved_data_dir.mkdir(parents=True, exist_ok=True)
    return settings.secret_key_path


def _fernet() -> Fernet:
    configured = settings.secret_key.strip()
    if configured:
        try:
            return Fernet(configured.encode("ascii"))
        except (ValueError, TypeError) as exc:
            raise RuntimeError("CONTRACT_ANALYZER_SECRET_KEY 必须是合法的 Fernet 密钥") from exc

    path = _key_file()
    if path.exists():
        return Fernet(path.read_bytes().strip())
    key = Fernet.generate_key()
    path.write_bytes(key)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return Fernet(key)


def encrypt_secret(value: str) -> str:
    if not value:
        return ""
    if value.startswith(PREFIX):
        return value
    return PREFIX + _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(value: str, *, allow_legacy_plaintext: bool = True) -> str:
    if not value:
        return ""
    if not value.startswith(PREFIX):
        if allow_legacy_plaintext:
            logger.warning("Found legacy plaintext secret; update the setting to encrypt it")
            return value
        raise RuntimeError("检测到未加密的旧密钥配置")
    try:
        return _fernet().decrypt(value[len(PREFIX) :].encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeDecodeError, ValueError) as exc:
        raise RuntimeError("密钥解密失败，请检查 CONTRACT_ANALYZER_SECRET_KEY") from exc


def get_secret_setting(db, key: str, default: str = "") -> str:
    from models.document import Setting

    return decrypt_secret(Setting.get(db, key, default))


def set_secret_setting(db, key: str, value: str) -> None:
    from models.document import Setting

    Setting.set(db, key, encrypt_secret(value))


def migrate_legacy_secrets(db) -> int:
    """Encrypt secrets stored by the recovered legacy application in place."""
    from models.document import Setting

    migrated = 0
    for key in ("deepseek_api_key", "baidu_ocr_api_key", "baidu_ocr_secret_key"):
        value = Setting.get(db, key, "")
        if value and not value.startswith(PREFIX):
            Setting.set(db, key, encrypt_secret(value))
            migrated += 1
    return migrated
