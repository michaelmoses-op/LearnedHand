import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import get_logger

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains",
}
# Swagger UI needs scripts/styles; relax the CSP only for the docs pages.
_DOCS_PATHS = {"/docs", "/redoc"}


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assigns a request ID, binds it to logs, adds security headers, logs the request."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        request.state.request_id = request_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id, user_id=None)
        start = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        for k, v in SECURITY_HEADERS.items():
            if k == "Content-Security-Policy" and request.url.path in _DOCS_PATHS:
                continue
            response.headers.setdefault(k, v)
        get_logger("access").info(
            "request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=round((time.perf_counter() - start) * 1000, 1),
        )
        return response
