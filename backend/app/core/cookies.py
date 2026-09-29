from dataclasses import dataclass

from fastapi import Response

from app.core.config import Settings


@dataclass(frozen=True)
class CookieNames:
    access: str
    refresh: str
    csrf: str


def cookie_names(settings: Settings) -> CookieNames:
    # __Host- requires Secure + Path=/; browsers reject it on plain-http localhost.
    if settings.cookie_secure:
        return CookieNames("__Host-access", "__Secure-refresh", "__Host-csrf")
    return CookieNames("access", "refresh", "csrf")


def set_auth_cookies(
    response: Response, settings: Settings, access: str, refresh: str, csrf: str
) -> None:
    n = cookie_names(settings)
    common = {"secure": settings.cookie_secure, "samesite": "lax"}
    response.set_cookie(
        n.access,
        access,
        max_age=settings.access_token_ttl_minutes * 60,
        httponly=True,
        path="/",
        **common,  # type: ignore[arg-type]
    )
    refresh_age = settings.refresh_token_ttl_days * 86400
    response.set_cookie(
        n.refresh,
        refresh,
        max_age=refresh_age,
        httponly=True,
        path="/api/v1/auth",
        **common,  # type: ignore[arg-type]
    )
    # Readable by JS on purpose: double-submit CSRF token.
    response.set_cookie(
        n.csrf,
        csrf,
        max_age=refresh_age,
        httponly=False,
        path="/",
        **common,  # type: ignore[arg-type]
    )


def clear_auth_cookies(response: Response, settings: Settings) -> None:
    n = cookie_names(settings)
    response.delete_cookie(n.access, path="/")
    response.delete_cookie(n.refresh, path="/api/v1/auth")
    response.delete_cookie(n.csrf, path="/")
