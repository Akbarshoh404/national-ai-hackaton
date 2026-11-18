"""Single error format for the whole API:

    {"error": {"code": "not_enough_market_data", "message": "...", "details": {...}}}
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("raft.errors")


class AppError(Exception):
    """Raise anywhere to return a structured error response."""

    def __init__(self, code: str, message: str, status: int = 400, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details = details or {}


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = {}


class ErrorResponse(BaseModel):
    error: ErrorBody


def not_found(what: str, id_: object = None) -> AppError:
    return AppError(f"{what}_not_found", f"{what.capitalize()} not found", 404, {"id": id_} if id_ else {})


def forbidden(message: str = "Not allowed") -> AppError:
    return AppError("forbidden", message, 403)


def conflict(code: str, message: str, details: dict[str, Any] | None = None) -> AppError:
    return AppError(code, message, 409, details)


def _body(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or {}}}


_HTTP_CODES = {400: "bad_request", 401: "unauthorized", 403: "forbidden", 404: "not_found",
               405: "method_not_allowed", 409: "conflict", 413: "payload_too_large",
               422: "validation_error", 503: "service_unavailable"}

#: Response docs added to every route so the OpenAPI client knows the error shape.
ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    code: {"model": ErrorResponse} for code in (400, 401, 403, 404, 409, 422)
}


def install(app: FastAPI) -> None:
    """Register exception handlers producing the unified error format."""

    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(_body(exc.code, exc.message, exc.details), status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [{"loc": [str(p) for p in e.get("loc", [])], "msg": e.get("msg"), "type": e.get("type")}
                  for e in exc.errors()]
        return JSONResponse(_body("validation_error", "Request validation failed", {"errors": errors}),
                            status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_CODES.get(exc.status_code, "error")
        return JSONResponse(_body(code, str(exc.detail)), status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error: %s", type(exc).__name__)
        return JSONResponse(_body("internal_error", "Internal server error"), status_code=500)
