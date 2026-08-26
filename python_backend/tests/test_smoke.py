"""Minimal offline smoke tests for the recovered FastAPI backend.

The tests call route functions directly so they do not require an HTTP client
dependency and never enter the application's lifespan.  A temporary SQLite
database and upload directory are used for every test; OCR and DeepSeek are
replaced with deterministic fakes.
"""

from __future__ import annotations

import asyncio
import io
import sys
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from starlette.datastructures import UploadFile


# Keep the test runnable from either ``python_backend`` or the repository root.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import main  # noqa: E402
import routers.analysis as analysis_router  # noqa: E402
import routers.documents as documents_router  # noqa: E402
import routers.ocr as ocr_router  # noqa: E402
from database import Base  # noqa: E402
from models.document import AnalysisResult, Document  # noqa: E402
from services.analysis_template_service import ensure_builtin_templates  # noqa: E402


class _FakeOcrService:
    def extract_text_from_pdf(self, stored_filename: str) -> dict:
        return {
            "full_text": "合同编号：SMOKE-001\n合同金额：1000元",
            "page_count": 1,
            "pages": [
                {
                    "page": 1,
                    "text": "合同编号：SMOKE-001\n合同金额：1000元",
                    "line_count": 2,
                    "avg_confidence": 1.0,
                    "lines": [
                        {"text": "合同编号：SMOKE-001", "confidence": 1.0},
                        {"text": "合同金额：1000元", "confidence": 1.0},
                    ],
                }
            ],
        }


class _FakeDeepSeekService:
    def analyze_document(self, document, template) -> list[dict]:
        return [
            {
                "prompt_type": "attribute_extraction",
                "prompt_text": "offline extraction prompt",
                "response_text": '{"contract_no":"SMOKE-001"}',
                "tokens_used": 3,
            },
            {
                "prompt_type": "reasonability_check",
                "prompt_text": "offline review prompt",
                "response_text": '{"数据问题":[],"内容合理性":[],"总结":"通过"}',
                "tokens_used": 5,
            },
        ]


class BackendSmokeTest(unittest.TestCase):
    """Exercise the core offline request flow without production state."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(prefix="contract-analyzer-test-")
        self.root = Path(self.temp_dir.name)
        db_path = self.root / "test.db"
        self.engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(bind=self.engine)
        self.Session = sessionmaker(bind=self.engine, autocommit=False, autoflush=False)
        self.db: Session = self.Session()
        ensure_builtin_templates(self.db)
        self.old_upload_dir = documents_router.UPLOAD_DIR
        documents_router.UPLOAD_DIR = self.root / "uploads"
        documents_router.UPLOAD_DIR.mkdir()

    def tearDown(self) -> None:
        documents_router.UPLOAD_DIR = self.old_upload_dir
        self.db.close()
        self.engine.dispose()
        self.temp_dir.cleanup()

    def test_health_endpoint_is_registered_and_offline(self) -> None:
        self.assertEqual(main.health_check(), {"status": "ok", "version": "1.0.0"})
        paths = {getattr(route, "path", None) for route in main.app.routes}
        self.assertIn("/api/health", paths)

    def test_upload_ocr_and_analysis_flow_uses_temp_state(self) -> None:
        upload = UploadFile(file=io.BytesIO(b"%PDF-1.4 offline smoke"), filename="smoke.pdf")
        uploaded = asyncio.run(
            documents_router.upload_document(file=upload, template_id=None, db=self.db)
        )
        self.assertEqual(uploaded.status, "uploaded")
        document = self.db.get(Document, uploaded.id)
        self.assertIsNotNone(document)
        self.assertTrue((documents_router.UPLOAD_DIR / document.stored_filename).exists())

        old_ocr_factory = ocr_router.get_ocr_service
        ocr_router.get_ocr_service = lambda: _FakeOcrService()
        try:
            ocr_result = ocr_router.process_ocr(document.id, self.db)
        finally:
            ocr_router.get_ocr_service = old_ocr_factory
        self.assertEqual(ocr_result.status, "ocr_done")
        self.assertEqual(ocr_result.page_count, 1)
        self.assertIn("SMOKE-001", ocr_result.text_preview)

        old_ai_factory = analysis_router.get_deepseek_service
        analysis_router.get_deepseek_service = lambda: _FakeDeepSeekService()
        try:
            analysis_result = analysis_router.analyze_document(document.id, None, self.db)
        finally:
            analysis_router.get_deepseek_service = old_ai_factory
        self.assertEqual(analysis_result.status, "done")
        self.assertEqual(len(analysis_result.results), 2)
        self.assertEqual(
            self.db.query(AnalysisResult).filter(AnalysisResult.document_id == document.id).count(),
            2,
        )

    def test_upload_rejects_non_pdf_without_writing(self) -> None:
        upload = UploadFile(file=io.BytesIO(b"not a pdf"), filename="notes.txt")
        with self.assertRaises(Exception) as raised:
            asyncio.run(
                documents_router.upload_document(file=upload, template_id=None, db=self.db)
            )
        self.assertEqual(getattr(raised.exception, "status_code", None), 400)
        self.assertEqual(self.db.query(Document).count(), 0)
        self.assertEqual(list(documents_router.UPLOAD_DIR.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
