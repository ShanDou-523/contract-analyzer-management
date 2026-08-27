"""FastAPI application entry point for Contract Analyzer backend."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from config import SERVER_HOST, SERVER_PORT, settings
from core.errors import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from core.logging import RequestContextMiddleware, configure_logging
from database import engine, init_db
from routers.analysis import router as analysis_router
from routers.analysis_templates import router as analysis_templates_router
from routers.auth import router as auth_router
from routers.contracts import router as contracts_router
from routers.documents import router as documents_router
from routers.export import router as export_router
from routers.fulfillment import router as fulfillment_router
from routers.ocr import router as ocr_router
from routers.settings import router as settings_router
from routers.users import router as users_router

configure_logging()
logger = logging.getLogger("contract_analyzer.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info("Initializing database environment=%s", settings.environment)
    init_db()
    logger.info("Database ready")
    logger.info("Server starting on http://%s:%s", SERVER_HOST, SERVER_PORT)
    yield
    logger.info("Server shutting down")


app = FastAPI(
    title="Contract Analyzer Backend",
    description="PDF OCR + DeepSeek Analysis API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestContextMiddleware)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)
app.include_router(documents_router)
app.include_router(ocr_router)
app.include_router(analysis_router)
app.include_router(settings_router)
app.include_router(export_router)
app.include_router(analysis_templates_router)
app.include_router(auth_router)
app.include_router(contracts_router)
app.include_router(fulfillment_router)
app.include_router(users_router)


@app.get("/api/health")
def health_check():
    """Health check endpoint used by Electron to detect backend readiness."""
    return {"status": "ok", "version": "1.0.0"}


@app.get("/api/health/ready")
def readiness_check():
    """Return dependency-level readiness diagnostics without exposing secrets."""
    from services.provider_health import (
        check_ai,
        check_database,
        check_ocr,
        check_redis,
        check_storage,
    )

    checks = {
        "database": check_database(engine),
        "redis": check_redis(),
        "storage": check_storage(),
        "ocr": check_ocr(),
        "ai": check_ai(),
    }
    required_ok = checks["database"]["status"] == "ok"
    return {
        "status": "ok" if required_ok else "error",
        "version": "1.0.0",
        "checks": checks,
    }


def main():
    """Entry point for running the server directly."""
    import uvicorn

    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT, log_level="info")


if __name__ == "__main__":
    main()
