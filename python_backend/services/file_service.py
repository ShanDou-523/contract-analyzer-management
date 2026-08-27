"""Safe storage helpers for contract file versions."""

from __future__ import annotations

import hashlib
import mimetypes
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

from config import settings

SUPPORTED_FILE_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".csv": "text/csv",
}


def extension_for(filename: str | None) -> str:
    return Path(filename or "").suffix.lower()


def validate_extension(filename: str | None) -> str:
    extension = extension_for(filename)
    if extension not in SUPPORTED_FILE_TYPES:
        supported = ", ".join(sorted(SUPPORTED_FILE_TYPES))
        raise HTTPException(status_code=400, detail=f"仅支持以下格式: {supported}")
    return extension


def mime_type_for(filename: str | None) -> str:
    extension = extension_for(filename)
    return SUPPORTED_FILE_TYPES.get(extension) or mimetypes.guess_type(filename or "")[0] or "application/octet-stream"


def upload_root() -> Path:
    root = settings.resolved_upload_dir / "contract-files"
    root.mkdir(parents=True, exist_ok=True)
    return root


def storage_path(storage_key: str) -> Path:
    """Resolve a generated or legacy storage key without allowing traversal."""
    root = settings.resolved_upload_dir.resolve()
    path = (root / storage_key).resolve()
    if path != root and root not in path.parents:
        raise HTTPException(status_code=400, detail="文件存储路径无效")
    return path


async def save_upload(upload: UploadFile, extension: str) -> tuple[str, int, str]:
    """Write a new file atomically and return storage key, size, and SHA-256."""
    upload_root()
    version_id = str(uuid.uuid4())
    storage_key = f"contract-files/{version_id}{extension}"
    destination = storage_path(storage_key)
    temporary = destination.with_suffix(destination.suffix + ".part")
    digest = hashlib.sha256()
    size = 0
    try:
        with temporary.open("wb") as handle:
            while chunk := await upload.read(1024 * 1024):
                size += len(chunk)
                if size > settings.max_file_size_bytes:
                    raise HTTPException(status_code=413, detail="文件超过大小限制")
                digest.update(chunk)
                handle.write(chunk)
        temporary.replace(destination)
        return storage_key, size, digest.hexdigest()
    except Exception:
        temporary.unlink(missing_ok=True)
        destination.unlink(missing_ok=True)
        raise


def remove_storage_key(storage_key: str | None) -> None:
    if not storage_key:
        return
    try:
        storage_path(storage_key).unlink(missing_ok=True)
    except (HTTPException, OSError):
        # Never let cleanup turn the original upload failure into a path error.
        return
