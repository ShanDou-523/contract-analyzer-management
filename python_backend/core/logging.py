"""Structured logging and request correlation helpers."""

from __future__ import annotations

import contextvars
import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")
user_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("user_id", default="-")
organization_id_var: contextvars.ContextVar[str] = contextvars.ContextVar(
    "organization_id", default="-"
)
task_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("task_id", default="-")


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        record.user_id = user_id_var.get()
        record.organization_id = organization_id_var.get()
        record.task_id = task_id_var.get()
        return True


def configure_logging() -> None:
    """Configure concise logs while keeping third-party libraries quiet."""
    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s request_id=%(request_id)s "
            "user_id=%(user_id)s organization_id=%(organization_id)s task_id=%(task_id)s %(message)s"
        )
    )
    handler.addFilter(RequestIdFilter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach a request ID and duration to every HTTP request."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        tokens = (
            request_id_var.set(request_id),
            user_id_var.set(request.headers.get("X-User-ID", "-")),
            organization_id_var.set(request.headers.get("X-Organization-ID", "-")),
            task_id_var.set(request.headers.get("X-Task-ID", "-")),
        )
        started = time.perf_counter()
        logger = logging.getLogger("contract_analyzer.http")
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        finally:
            elapsed_ms = (time.perf_counter() - started) * 1000
            logger.info("%s %s completed in %.1fms", request.method, request.url.path, elapsed_ms)
            request_id_var.reset(tokens[0])
            user_id_var.reset(tokens[1])
            organization_id_var.reset(tokens[2])
            task_id_var.reset(tokens[3])
