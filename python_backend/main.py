"""FastAPI application entry point for Contract Analyzer backend."""

import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import SERVER_HOST, SERVER_PORT
from database import init_db
from routers.documents import router as documents_router
from routers.ocr import router as ocr_router
from routers.analysis import router as analysis_router
from routers.settings import router as settings_router
from routers.export import router as export_router
from routers.analysis_templates import router as analysis_templates_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    print("[ContractAnalyzer] Initializing database...")
    init_db()
    print("[ContractAnalyzer] Database ready.")
    print(f"[ContractAnalyzer] Server starting on http://{SERVER_HOST}:{SERVER_PORT}")
    yield
    print("[ContractAnalyzer] Server shutting down.")


app = FastAPI(
    title="Contract Analyzer Backend",
    description="PDF OCR + DeepSeek Analysis API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(documents_router)
app.include_router(ocr_router)
app.include_router(analysis_router)
app.include_router(settings_router)
app.include_router(export_router)
app.include_router(analysis_templates_router)


@app.get("/api/health")
def health_check():
    """Health check endpoint used by Electron to detect backend readiness."""
    return {"status": "ok", "version": "1.0.0"}


def main():
    """Entry point for running the server directly."""
    import uvicorn

    uvicorn.run(app, host=SERVER_HOST, port=SERVER_PORT, log_level="info")


if __name__ == "__main__":
    main()
