from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class ApiError(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: list[dict[str, Any]] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or []
        self.headers = headers or {}


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", None) or request.headers.get("X-Request-ID") or f"req_{uuid.uuid4().hex[:20]}"


def error_response(request: Request, status_code: int, code: str, message: str, details=None, headers=None):
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details or [],
                "request_id": _request_id(request),
            }
        },
        headers=headers,
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError):
        return error_response(request, exc.status_code, exc.code, exc.message, exc.details, exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError):
        details = []
        for item in exc.errors():
            loc = ".".join(str(part) for part in item.get("loc", []) if part not in {"body", "query", "path"})
            details.append({"field": loc or "request", "issue": item.get("msg", "invalid value")})
        return error_response(request, 400, "VALIDATION_FAILED", "One or more fields are invalid.", details)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        # Do not leak exception details to clients.
        logger.exception("unhandled error request_id=%s", _request_id(request))
        return error_response(request, 500, "INTERNAL_ERROR", "An unexpected error occurred.")
