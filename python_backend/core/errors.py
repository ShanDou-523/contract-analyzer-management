"""Stable API error responses."""

from __future__ import annotations

import logging

from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from core.logging import request_id_var

logger = logging.getLogger("contract_analyzer.errors")


def error_payload(code: str, message: str, details=None) -> dict:
    return {
        "code": code,
        "message": message,
        "details": details,
        "request_id": request_id_var.get(),
    }


async def http_exception_handler(_request: Request, exc: StarletteHTTPException):
    detail = exc.detail if isinstance(exc.detail, (str, dict, list)) else str(exc.detail)
    message = detail if isinstance(detail, str) else "请求失败"
    return JSONResponse(
        status_code=exc.status_code,
        content=error_payload(
            f"HTTP_{exc.status_code}", message, None if isinstance(detail, str) else detail
        ),
        headers=exc.headers,
    )


async def validation_exception_handler(_request: Request, exc: RequestValidationError):
    details = []
    for error in exc.errors():
        item = dict(error)
        if isinstance(item.get("ctx"), dict):
            item["ctx"] = {
                key: str(value) if isinstance(value, BaseException) else value
                for key, value in item["ctx"].items()
            }
        details.append(item)
    return JSONResponse(
        status_code=422,
        content=jsonable_encoder(
            error_payload("VALIDATION_ERROR", "请求参数校验失败", details)
        ),
    )


async def unhandled_exception_handler(_request: Request, exc: Exception):
    logger.exception("Unhandled server exception")
    return JSONResponse(
        status_code=500,
        content=error_payload("INTERNAL_SERVER_ERROR", "服务器内部错误", None),
    )
