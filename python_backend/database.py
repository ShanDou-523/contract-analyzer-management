"""Database engine and session factory."""

import shutil

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from config import DATABASE_URL, DB_PATH

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
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


def init_db():
    """Create tables, apply additive migrations, and seed built-in templates."""
    from models.document import AnalysisResult, AnalysisTemplate, Document, Setting
    from sqlalchemy.orm import configure_mappers

    configure_mappers()
    Base.metadata.create_all(bind=engine)

    migration_columns = {
        "template_id": "VARCHAR(36)",
        "template_name": "VARCHAR(100)",
        "template_version": "INTEGER",
        "fields_snapshot_json": "TEXT",
    }
    document_columns = {
        "analysis_template_id": "VARCHAR(36)",
        "analysis_template_name": "VARCHAR(100)",
        "analysis_template_version": "INTEGER",
    }
    with engine.begin() as connection:
        existing_results = {
            row[1]
            for row in connection.exec_driver_sql(
                "PRAGMA table_info(analysis_results)"
            ).fetchall()
        }
        existing_documents = {
            row[1]
            for row in connection.exec_driver_sql(
                "PRAGMA table_info(documents)"
            ).fetchall()
        }
        missing = [
            *(name for name in migration_columns if name not in existing_results),
            *(name for name in document_columns if name not in existing_documents),
        ]
        if missing and DB_PATH.exists():
            backup_path = DB_PATH.with_name(f"{DB_PATH.stem}.pre_template_assignment.bak")
            if not backup_path.exists():
                shutil.copy2(DB_PATH, backup_path)
        for name in migration_columns:
            if name not in existing_results:
                connection.exec_driver_sql(
                    f"ALTER TABLE analysis_results ADD COLUMN {name} {migration_columns[name]}"
                )
        for name in document_columns:
            if name not in existing_documents:
                connection.exec_driver_sql(
                    f"ALTER TABLE documents ADD COLUMN {name} {document_columns[name]}"
                )
        connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_documents_analysis_template_id "
            "ON documents (analysis_template_id)"
        )

    db = SessionLocal()
    try:
        _backfill_document_templates(db)
    finally:
        db.close()

    from services.analysis_template_service import ensure_builtin_templates

    db = SessionLocal()
    try:
        ensure_builtin_templates(db)
    finally:
        db.close()


def _backfill_document_templates(db):
    """Associate legacy documents with the latest successful analysis template."""
    from models.document import AnalysisResult, AnalysisTemplate, Document

    documents = db.query(Document).filter(Document.analysis_template_id.is_(None)).all()
    changed = False
    for document in documents:
        result = db.query(AnalysisResult).filter(
            AnalysisResult.document_id == document.id,
            AnalysisResult.template_id.isnot(None),
        ).order_by(AnalysisResult.created_at.desc()).first()
        if result:
            template_exists = db.query(AnalysisTemplate).filter(
                AnalysisTemplate.id == result.template_id
            ).first()
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
