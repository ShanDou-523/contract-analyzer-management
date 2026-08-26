"""Stage 2 historical-data migration and reconciliation tests."""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database import Base
from models.contract import AnalysisRun, Contract, ContractFile, FileVersion, Organization, User
from models.document import AnalysisResult, AnalysisTemplate, Document
from services.domain_migration import migrate_legacy_data


def test_empty_legacy_migration_does_not_create_placeholder_identity(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'empty.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    report = migrate_legacy_data(session, tmp_path / "uploads")

    assert report["source_counts"]["documents"] == 0
    assert session.query(Organization).count() == 0
    assert session.query(User).count() == 0
    session.close()
    engine.dispose()


def test_legacy_migration_is_idempotent_and_keeps_mapping(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path / 'stage2.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    template = AnalysisTemplate(
        id="template-stage2",
        name="阶段2测试方案",
        description="test",
        analysis_focus="test focus",
        fields_json="[]",
        review_enabled=True,
        review_instructions="",
        version=1,
        is_default=True,
    )
    document = Document(
        id="document-stage2",
        original_filename="阶段2测试合同.pdf",
        stored_filename="document-stage2.pdf",
        file_size=14,
        status="done",
        ocr_text="合同编号：STAGE2-001",
        page_count=1,
        analysis_template_id=template.id,
        analysis_template_name=template.name,
        analysis_template_version=1,
    )
    result = AnalysisResult(
        id="result-stage2",
        document_id=document.id,
        prompt_type="attribute_extraction",
        prompt_text="test prompt",
        response_text='{"contract_no":"STAGE2-001"}',
        tokens_used=7,
        template_id=template.id,
        template_name=template.name,
        template_version=1,
    )
    session.add_all([template, document, result])
    session.commit()

    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    (upload_dir / document.stored_filename).write_bytes(b"stage2-pdf-data")
    report_path = tmp_path / "migration-report.json"

    first = migrate_legacy_data(session, upload_dir, report_path)
    second = migrate_legacy_data(session, upload_dir, report_path)

    assert first["source_counts"] == {
        "documents": 1,
        "analysis_results": 1,
        "analysis_templates": 1,
    }
    assert first["target_counts"] == second["target_counts"]
    assert first["target_counts"]["contracts"] == 1
    assert first["target_counts"]["contract_files"] == 1
    assert first["target_counts"]["file_versions"] == 1
    assert first["target_counts"]["analysis_template_versions"] == 1
    assert first["target_counts"]["analysis_runs"] == 1
    assert first["missing_files"] == []

    contract = session.query(Contract).one()
    contract_file = session.query(ContractFile).one()
    file_version = session.query(FileVersion).one()
    run = session.query(AnalysisRun).one()
    migrated_result = session.query(AnalysisResult).one()
    assert contract.legacy_document_id == document.id
    assert contract_file.current_version_id == file_version.id
    assert file_version.sha256
    assert run.contract_id == contract.id
    assert migrated_result.analysis_run_id == run.id

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["contract_mappings"][0]["document_id"] == document.id
    assert report["analysis_run_mappings"][0]["analysis_run_id"] == run.id

    session.close()
    engine.dispose()
