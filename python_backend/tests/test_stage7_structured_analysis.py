"""Stage 7 structured analysis, evidence, risk, and review tests."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

import config
import database
import main
from alembic import command
from core import security
from models.contract import (
    AnalysisRun,
    AuditLog,
    Base,
    Contract,
    Organization,
    StructuredAnalysisResult,
    User,
)
from models.document import AnalysisResult, AnalysisTemplate, Document
from routers import analysis as analysis_router
from services import auth_service


def _settings(tmp_path: Path):
    data_dir = tmp_path / "data"
    return SimpleNamespace(
        environment="local",
        jwt_secret_key="stage7-test-secret",
        jwt_secret_key_path=data_dir / "jwt.key",
        access_token_expire_minutes=30,
        refresh_token_expire_days=14,
        max_login_attempts=3,
        lockout_minutes=15,
        admin_username="",
        admin_password="",
        resolved_data_dir=data_dir,
        resolved_upload_dir=data_dir / "uploads",
        max_file_size_bytes=5 * 1024 * 1024,
        secret_key="",
        secret_key_path=data_dir / "secret.key",
    )


class _FakeDeepSeek:
    def analyze_document(self, _document, _template):
        return [
            {
                "prompt_type": "attribute_extraction",
                "prompt_text": "extract",
                "response_text": json.dumps(
                    {"contract_no": "S7-001", "amount": "100000.00"},
                    ensure_ascii=False,
                ),
                "tokens_used": 11,
            },
            {
                "prompt_type": "reasonability_check",
                "prompt_text": "review",
                "response_text": json.dumps(
                    {
                        "数据问题": [
                            {
                                "项目": "付款期限",
                                "是否有问题": "是",
                                "严重程度": "警告",
                                "合同标注": "乙方开票后九十日内付款",
                                "说明": "付款周期偏长，需要业务确认。",
                            }
                        ],
                        "内容合理性": [
                            {"方面": "付款安排", "评价": "需复核", "建议": "确认资金计划"}
                        ],
                        "总结": "发现一项付款期限风险。",
                    },
                    ensure_ascii=False,
                ),
                "tokens_used": 19,
            },
        ]


def test_stage7_migration_adds_structured_review_tables(tmp_path: Path):
    database_path = tmp_path / "migration.db"
    alembic_config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(Path(__file__).parents[1] / "alembic"))
    alembic_config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")

    command.upgrade(alembic_config, "head")

    engine = create_engine(f"sqlite:///{database_path}")
    tables = set(inspect(engine).get_table_names())
    assert {
        "structured_analysis_results",
        "structured_analysis_fields",
        "analysis_evidence",
        "analysis_risks",
    } <= tables
    columns = {
        column["name"] for column in inspect(engine).get_columns("structured_analysis_results")
    }
    assert {
        "organization_id",
        "contract_id",
        "analysis_run_id",
        "source_result_id",
        "file_version_id",
        "template_version_id",
        "version",
        "status",
    } <= columns
    engine.dispose()


def test_analysis_history_import_review_versioning_and_scope(tmp_path: Path, monkeypatch):
    database_path = tmp_path / "stage7.db"
    engine = create_engine(f"sqlite:///{database_path}")
    Base.metadata.create_all(engine)
    local_session = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    test_settings = _settings(tmp_path)
    monkeypatch.setattr(database, "SessionLocal", local_session)
    monkeypatch.setattr(database, "DATABASE_URL", f"sqlite:///{database_path}")
    monkeypatch.setattr(security, "settings", test_settings)
    monkeypatch.setattr(auth_service, "settings", test_settings)
    monkeypatch.setattr(config, "settings", test_settings)
    monkeypatch.setattr(analysis_router, "get_deepseek_service", lambda: _FakeDeepSeek())

    client = TestClient(main.app)
    bootstrap = client.post(
        "/api/v1/auth/bootstrap",
        json={
            "organization_name": "阶段7组织",
            "organization_code": "stage7",
            "username": "admin",
            "password": "stage7-password",
            "display_name": "阶段7管理员",
        },
    )
    assert bootstrap.status_code == 201, bootstrap.text
    admin = bootstrap.json()["user"]
    headers = {"Authorization": f"Bearer {bootstrap.json()['access_token']}"}

    db = local_session()
    template = AnalysisTemplate(
        organization_id=admin["organization_id"],
        name="阶段7分析方案",
        fields_json=json.dumps(
            [
                {"key": "contract_no", "label": "合同编号", "enabled": True},
                {"key": "amount", "label": "合同金额", "enabled": True},
            ],
            ensure_ascii=False,
        ),
        version=1,
        is_default=True,
    )
    document = Document(
        organization_id=admin["organization_id"],
        original_filename="阶段7合同.pdf",
        stored_filename="stage7.pdf",
        file_size=1024,
        status="ocr_done",
        ocr_text="合同编号 S7-001，乙方开票后九十日内付款。",
        page_count=1,
    )
    db.add_all([template, document])
    db.flush()
    old_result = AnalysisResult(
        document_id=document.id,
        prompt_type="attribute_extraction",
        prompt_text="historical prompt",
        response_text='{"contract_no":"HISTORICAL"}',
        template_id=template.id,
        template_name=template.name,
        template_version=1,
    )
    db.add(old_result)
    db.commit()
    document_id = document.id
    template_id = template.id
    old_result_id = old_result.id
    db.close()

    analyzed = client.post(
        f"/api/analysis/{document_id}/analyze",
        headers=headers,
        json={"template_id": template_id},
    )
    assert analyzed.status_code == 200, analyzed.text
    assert len(analyzed.json()["results"]) == 2

    db = local_session()
    assert db.query(AnalysisResult).filter(AnalysisResult.document_id == document_id).count() == 3
    assert db.get(AnalysisResult, old_result_id).response_text == '{"contract_no":"HISTORICAL"}'
    contract = db.query(Contract).filter(Contract.legacy_document_id == document_id).one()
    contract_id = contract.id
    run = db.query(AnalysisRun).filter(AnalysisRun.contract_id == contract_id).one()
    assert run.status == "succeeded"
    assert run.file_version_id is not None
    assert run.template_version_id is not None
    assert run.output_tokens == 30
    run_id = run.id
    db.close()

    imported = client.post(
        f"/api/v1/analysis-runs/{run_id}/structured-results/import-legacy",
        headers=headers,
    )
    assert imported.status_code == 200, imported.text
    imported_results = imported.json()
    assert {item["prompt_type"] for item in imported_results} == {
        "attribute_extraction",
        "reasonability_check",
    }
    attribute = next(
        item for item in imported_results if item["prompt_type"] == "attribute_extraction"
    )
    review = next(
        item for item in imported_results if item["prompt_type"] == "reasonability_check"
    )
    assert [field["label"] for field in attribute["fields"]] == ["合同编号", "合同金额"]
    assert review["summary"] == "发现一项付款期限风险。"
    assert review["risks"][0]["severity"] == "high"
    assert review["evidence"][0]["quote"] == "乙方开票后九十日内付款"
    assert review["risks"][0]["evidence_id"] == review["evidence"][0]["id"]

    repeated = client.post(
        f"/api/v1/analysis-runs/{run_id}/structured-results/import-legacy",
        headers=headers,
    )
    assert {item["id"] for item in repeated.json()} == {item["id"] for item in imported_results}

    viewer = client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "username": "stage7-viewer",
            "password": "stage7-viewer-password",
            "display_name": "阶段7只读用户",
            "roles": ["viewer"],
        },
    )
    assert viewer.status_code == 201
    reviewer = client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "username": "stage7-reviewer",
            "password": "stage7-review-password",
            "display_name": "阶段7复核员",
            "roles": ["reviewer"],
        },
    )
    assert reviewer.status_code == 201
    viewer_login = client.post(
        "/api/v1/auth/login",
        json={"username": "stage7-viewer", "password": "stage7-viewer-password"},
    )
    reviewer_login = client.post(
        "/api/v1/auth/login",
        json={"username": "stage7-reviewer", "password": "stage7-review-password"},
    )
    viewer_headers = {"Authorization": f"Bearer {viewer_login.json()['access_token']}"}
    reviewer_headers = {"Authorization": f"Bearer {reviewer_login.json()['access_token']}"}
    assert (
        client.get(f"/api/v1/contracts/{contract_id}/analysis-runs", headers=viewer_headers).status_code
        == 200
    )
    assert (
        client.post(
            f"/api/v1/analysis-runs/{run_id}/structured-results/{review['id']}/submit",
            headers=viewer_headers,
        ).status_code
        == 403
    )

    submitted_review = client.post(
        f"/api/v1/analysis-runs/{run_id}/structured-results/{review['id']}/submit",
        headers=headers,
    )
    assert submitted_review.status_code == 200
    assert submitted_review.json()["status"] == "in_review"
    risk_id = submitted_review.json()["risks"][0]["id"]
    missing_comment = client.patch(
        f"/api/v1/analysis-runs/{run_id}/structured-results/{review['id']}/risks/{risk_id}",
        headers=reviewer_headers,
        json={"status": "accepted", "comment": ""},
    )
    assert missing_comment.status_code == 422
    reviewed_risk = client.patch(
        f"/api/v1/analysis-runs/{run_id}/structured-results/{review['id']}/risks/{risk_id}",
        headers=reviewer_headers,
        json={"status": "accepted", "comment": "业务已确认接受较长付款周期"},
    )
    assert reviewed_risk.status_code == 200, reviewed_risk.text
    assert reviewed_risk.json()["risks"][0]["status"] == "accepted"
    approved = client.post(
        f"/api/v1/analysis-runs/{run_id}/structured-results/{review['id']}/review",
        headers=reviewer_headers,
        json={"decision": "approved", "comment": "风险已确认"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    assert (
        client.post(
            f"/api/v1/analysis-runs/{run_id}/structured-results/{review['id']}/revisions",
            headers=headers,
            json={"summary": "不应允许修改已批准版本"},
        ).status_code
        == 409
    )

    client.post(
        f"/api/v1/analysis-runs/{run_id}/structured-results/{attribute['id']}/submit",
        headers=headers,
    )
    rejected = client.post(
        f"/api/v1/analysis-runs/{run_id}/structured-results/{attribute['id']}/review",
        headers=reviewer_headers,
        json={"decision": "rejected", "comment": "合同金额需要注明币种"},
    )
    assert rejected.status_code == 200
    revision = client.post(
        f"/api/v1/analysis-runs/{run_id}/structured-results/{attribute['id']}/revisions",
        headers=headers,
        json={
            "summary": "补充币种后重新提交",
            "fields": [
                {
                    "field_key": "amount",
                    "label": "合同金额",
                    "value": {"amount": "100000.00", "currency": "CNY"},
                    "confidence": 0.98,
                }
            ],
        },
    )
    assert revision.status_code == 201, revision.text
    assert revision.json()["version"] == 2
    assert revision.json()["status"] == "draft"
    all_versions = client.get(
        f"/api/v1/analysis-runs/{run_id}/structured-results", headers=headers
    )
    attribute_versions = [
        item for item in all_versions.json() if item["prompt_type"] == "attribute_extraction"
    ]
    assert [item["version"] for item in attribute_versions] == [2, 1]
    assert attribute_versions[1]["status"] == "superseded"

    invalid_evidence = client.post(
        f"/api/v1/analysis-runs/{run_id}/structured-results",
        headers=headers,
        json={
            "prompt_type": "custom_check",
            "evidence": [{"char_end": 12, "quote": "invalid"}],
        },
    )
    assert invalid_evidence.status_code == 422

    db = local_session()
    foreign_org = Organization(name="阶段7其他组织", code="stage7-foreign")
    db.add(foreign_org)
    db.flush()
    foreign_user = User(
        organization_id=foreign_org.id,
        username="stage7-foreign-user",
        display_name="其他组织用户",
        status="active",
    )
    db.add(foreign_user)
    db.flush()
    foreign_contract = Contract(
        organization_id=foreign_org.id,
        name="其他组织合同",
        created_by=foreign_user.id,
        updated_by=foreign_user.id,
    )
    db.add(foreign_contract)
    db.flush()
    foreign_run = AnalysisRun(contract_id=foreign_contract.id, status="succeeded")
    db.add(foreign_run)
    db.commit()
    foreign_run_id = foreign_run.id
    foreign_contract_id = foreign_contract.id
    assert db.query(StructuredAnalysisResult).count() == 3
    assert db.query(AuditLog).filter(AuditLog.action == "analysis.risk_reviewed").count() == 1
    db.close()

    assert client.get(f"/api/v1/analysis-runs/{foreign_run_id}", headers=headers).status_code == 404
    assert (
        client.get(
            f"/api/v1/contracts/{foreign_contract_id}/analysis-runs", headers=headers
        ).status_code
        == 404
    )
    engine.dispose()
