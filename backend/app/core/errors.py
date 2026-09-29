from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

PROBLEM_JSON = "application/problem+json"


class DomainError(Exception):
    """Base for domain errors; maps to an RFC 7807 response with a stable `code`."""

    status = 400
    code = "domain_error"
    title = "Bad request"

    def __init__(self, detail: str | None = None, headers: dict[str, str] | None = None) -> None:
        super().__init__(detail or self.title)
        self.detail = detail or self.title
        self.headers = headers or {}


class NotFoundError(DomainError):
    status = 404
    code = "not_found"
    title = "Resource not found"


class UnauthenticatedError(DomainError):
    status = 401
    code = "unauthenticated"
    title = "Authentication required"


class ForbiddenError(DomainError):
    status = 403
    code = "forbidden"
    title = "Forbidden"


class CsrfError(ForbiddenError):
    code = "csrf_failed"
    title = "CSRF validation failed"


class ConflictError(DomainError):
    status = 409
    code = "conflict"
    title = "Conflict"


class PayloadTooLargeError(DomainError):
    status = 413
    code = "payload_too_large"
    title = "Payload too large"


class UnsupportedFileError(DomainError):
    status = 415
    code = "unsupported_file"
    title = "Unsupported file type"


class RateLimitedError(DomainError):
    status = 429
    code = "rate_limited"
    title = "Too many requests"


def problem(
    request: Request,
    status: int,
    code: str,
    title: str,
    detail: str | None = None,
    headers: dict[str, str] | None = None,
    **extra: Any,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": "about:blank",
        "title": title,
        "status": status,
        "code": code,
        "detail": detail or title,
        "instance": request.url.path,
        "request_id": getattr(request.state, "request_id", None),
        **extra,
    }
    return JSONResponse(body, status_code=status, media_type=PROBLEM_JSON, headers=headers)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain(request: Request, exc: DomainError) -> JSONResponse:
        return problem(request, exc.status, exc.code, exc.title, exc.detail, exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Do not echo input values back (they may contain document text or secrets).
        errors = [{"loc": e["loc"], "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
        return problem(request, 422, "validation_error", "Validation failed", errors=errors)

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = "not_found" if exc.status_code == 404 else "http_error"
        return problem(request, exc.status_code, code, str(exc.detail))

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        from app.core.logging import get_logger

        get_logger(__name__).error("unhandled_exception", exc_info=exc)
        return problem(request, 500, "internal_error", "Internal server error")
