"""Database engine, sessions, and Alembic-backed initialization."""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, configure_mappers, sessionmaker

from alembic import command
from config import BASE_DIR, DATABASE_URL, ensure_runtime_dirs, settings

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
    echo=False,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency: yields a DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _alembic_config() -> Config:
    config = Config(str(Path(BASE_DIR) / "alembic.ini"))
    config.set_main_option("script_location", str(Path(BASE_DIR) / "alembic"))
    config.set_main_option("sqlalchemy.url", DATABASE_URL.replace("%", "%%"))
    return config


def run_migrations() -> None:
    """Upgrade the configured database to the current schema revision."""
    ensure_runtime_dirs()
    configure_mappers()
    command.upgrade(_alembic_config(), "head")


def init_db() -> None:
    """Run migrations, legacy backfill, and built-in template seeding."""
    from services.analysis_template_service import ensure_builtin_templates
    from services.domain_migration import migrate_legacy_data
    from services.secret_service import migrate_legacy_secrets

    run_migrations()
    db = SessionLocal()
    try:
        migrated_secrets = migrate_legacy_secrets(db)
        if migrated_secrets:
            import logging

            logging.getLogger("contract_analyzer.database").info(
                "Migrated %s legacy plaintext secret(s)", migrated_secrets
            )
        _backfill_document_templates(db)
        ensure_builtin_templates(db)
        migrate_legacy_data(
            db,
            settings.resolved_upload_dir,
            settings.resolved_data_dir / "migration_reports" / "stage2_legacy_migration.json",
        )
    finally:
        db.close()


def _backfill_document_templates(db) -> None:
    """Associate legacy documents with the latest successful analysis template."""
    from models.document import AnalysisResult, AnalysisTemplate, Document

    documents = db.query(Document).filter(Document.analysis_template_id.is_(None)).all()
    changed = False
    for document in documents:
        result = (
            db.query(AnalysisResult)
            .filter(
                AnalysisResult.document_id == document.id,
                AnalysisResult.template_id.isnot(None),
            )
            .order_by(AnalysisResult.created_at.desc())
            .first()
        )
        if result:
            template_exists = (
                db.query(AnalysisTemplate).filter(AnalysisTemplate.id == result.template_id).first()
            )
            document.analysis_template_id = result.template_id if template_exists else None
            document.analysis_template_name = (
                result.template_name
                if template_exists
                else f"{result.template_name or '历史方案'}（已删除）"
            )
            document.analysis_template_version = result.template_version
            changed = True
    if changed:
        db.commit()
