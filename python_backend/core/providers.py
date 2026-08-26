"""Provider protocols used to keep OCR and AI integrations replaceable."""

from __future__ import annotations

from typing import Any, Protocol


class OcrProvider(Protocol):
    def extract_text_from_pdf(self, stored_filename: str) -> dict[str, Any]: ...


class AnalysisProvider(Protocol):
    def analyze_document(self, document, template) -> list[dict[str, Any]]: ...


class FileStorageProvider(Protocol):
    def save(self, storage_key: str, content: bytes) -> str: ...

    def exists(self, storage_key: str) -> bool: ...

    def delete(self, storage_key: str) -> None: ...


class DatabaseSessionProvider(Protocol):
    def __call__(self): ...
