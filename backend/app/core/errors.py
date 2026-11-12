"""Consistent JSON error responses: ``{"error": {"code", "message", "details"}}``.

Error bodies never include exception messages from lower layers (they may contain connection
details); unexpected errors return a generic ``internal_error``.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("volterra.api")

HTTP_CODES = {404: "not_found", 405: "method_not_allowed"}


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: list[dict[str, Any]] | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


class ApiError(Exception):
    """An expected API error with a stable machine-readable ``code``."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


def not_found(resource: str, identifier: object) -> ApiError:
    return ApiError(404, f"{resource}_not_found", f"{resource.capitalize()} {identifier} not found")


def _body(code: str, message: str, details: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return ErrorResponse(error=ErrorDetail(code=code, message=message, details=details)).model_dump(
        exclude_none=True
    )


async def _api_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ApiError)
    return JSONResponse(_body(exc.code, exc.message, exc.details), status_code=exc.status_code)


async def _validation_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    details = [
        {
            "loc": list(e.get("loc", ())),
            "msg": str(e.get("msg", "")),
            "type": str(e.get("type", "")),
        }
        for e in exc.errors()
    ]
    return JSONResponse(
        _body("validation_error", "Request validation failed", details), status_code=422
    )


async def _http_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    code = HTTP_CODES.get(exc.status_code, "http_error")
    return JSONResponse(_body(code, str(exc.detail)), status_code=exc.status_code)


async def _unexpected_error(_: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled error: %s", type(exc).__name__)
    return JSONResponse(_body("internal_error", "Internal server error"), status_code=500)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ApiError, _api_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(Exception, _unexpected_error)
