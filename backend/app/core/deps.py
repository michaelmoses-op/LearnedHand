import secrets
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Annotated

import structlog
from fastapi import Depends, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.cookies import cookie_names
from app.core.errors import CsrfError, UnauthenticatedError
from app.core.ratelimit import RateLimiter
from app.core.security import decode_access_token
from app.services.mailer import Mailer
from app.storage.base import Storage

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


@dataclass(frozen=True)
class AuthContext:
    """Identity every repository method requires. There is no way to query without one."""

    user_id: uuid.UUID


async def set_rls_user(session: AsyncSession, user_id: uuid.UUID) -> None:
    # set_config(..., is_local=true) == SET LOCAL: scoped to the current transaction.
    await session.execute(
        text("select set_config('app.current_user_id', :uid, true)"), {"uid": str(user_id)}
    )


def get_settings_dep(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


SettingsDep = Annotated[Settings, Depends(get_settings_dep)]


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    """Unscoped session (public/auth endpoints). Handlers commit explicitly; an exception
    or early return without commit rolls back."""
    async with request.app.state.sessionmaker() as session:
        yield session


def get_rate_limiter(request: Request) -> RateLimiter:
    limiter: RateLimiter = request.app.state.limiter
    return limiter


def get_mailer(request: Request) -> Mailer:
    mailer: Mailer = request.app.state.mailer
    return mailer


def get_storage(request: Request) -> Storage:
    storage: Storage = request.app.state.storage
    return storage


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def origin_check(request: Request, settings: SettingsDep) -> None:
    """Reject browser requests from origins outside the allowlist (state-changing only)."""
    if request.method in SAFE_METHODS:
        return
    origin = request.headers.get("origin")
    if origin is not None and not settings.origin_allowed(origin):
        raise CsrfError(f"Origin not allowed: {origin[:100]} (add it to CORS_ORIGINS)")


def csrf_protect(request: Request, settings: SettingsDep) -> None:
    """Origin check + double-submit token for cookie-authenticated state-changing requests."""
    if request.method in SAFE_METHODS:
        return
    origin_check(request, settings)
    names = cookie_names(settings)
    if names.access not in request.cookies and names.refresh not in request.cookies:
        return  # no ambient credentials => nothing to forge; the endpoint will answer 401
    cookie = request.cookies.get(names.csrf)
    header = request.headers.get("x-csrf-token")
    if not cookie or not header or not secrets.compare_digest(cookie, header):
        raise CsrfError()


def current_auth(request: Request, settings: SettingsDep) -> AuthContext:
    token = request.cookies.get(cookie_names(settings).access)
    user_id = decode_access_token(token, settings.secret_key) if token else None
    if user_id is None:
        raise UnauthenticatedError()
    structlog.contextvars.bind_contextvars(user_id=str(user_id))
    return AuthContext(user_id)


AuthDep = Annotated[AuthContext, Depends(current_auth)]


async def get_auth_db(request: Request, auth: AuthDep) -> AsyncIterator[AsyncSession]:
    """Session whose transaction is bound to the caller via Postgres RLS."""
    async with request.app.state.sessionmaker() as session:
        await set_rls_user(session, auth.user_id)
        yield session


DbDep = Annotated[AsyncSession, Depends(get_db)]
AuthDbDep = Annotated[AsyncSession, Depends(get_auth_db)]
LimiterDep = Annotated[RateLimiter, Depends(get_rate_limiter)]
MailerDep = Annotated[Mailer, Depends(get_mailer)]
StorageDep = Annotated[Storage, Depends(get_storage)]
