import uuid

from fastapi import FastAPI
from httpx import AsyncClient

from app.core.ratelimit import RateLimiter
from tests.conftest import PASSWORD, CapturingMailer, build_client, register_and_login

A = "/api/v1/auth"


def _email() -> str:
    return f"{uuid.uuid4().hex[:12]}@example.com"


async def test_signup_is_generic_for_new_and_existing(
    client: AsyncClient, mailer: CapturingMailer
) -> None:
    email = _email()
    r1 = await client.post(f"{A}/signup", json={"email": email, "password": PASSWORD})
    r2 = await client.post(f"{A}/signup", json={"email": email, "password": PASSWORD})
    assert r1.status_code == r2.status_code == 202
    assert r1.json() == r2.json()
    subjects = [s for to, s, _ in mailer.sent if to == email]
    assert "Verify your email" in subjects and "Sign-up attempt" in subjects


async def test_password_policy_and_extra_fields_rejected(client: AsyncClient) -> None:
    r = await client.post(f"{A}/signup", json={"email": _email(), "password": "short"})
    assert r.status_code == 422
    r = await client.post(
        f"{A}/signup", json={"email": _email(), "password": PASSWORD, "is_admin": True}
    )
    assert r.status_code == 422


async def test_login_sets_hardened_cookies_and_me_works(client: AsyncClient) -> None:
    email = await register_and_login(client)
    set_cookies = client.cookies.jar
    names = {c.name: c for c in set_cookies}
    assert {"access", "refresh", "csrf"} <= names.keys()
    assert names["access"].has_nonstandard_attr("HttpOnly")
    assert names["refresh"].has_nonstandard_attr("HttpOnly")
    assert not names["csrf"].has_nonstandard_attr("HttpOnly")
    assert names["refresh"].path == "/api/v1/auth"
    me = await client.get(f"{A}/me")
    assert me.status_code == 200 and me.json()["email"] == email


async def test_login_failures_do_not_reveal_email_existence(client: AsyncClient) -> None:
    email = await register_and_login(client)
    async with build_client(client._transport.app) as anon:  # type: ignore[attr-defined]
        wrong = await anon.post(f"{A}/login", json={"email": email, "password": "x" * 14})
        unknown = await anon.post(f"{A}/login", json={"email": _email(), "password": "x" * 14})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["code"] == unknown.json()["code"] == "invalid_credentials"
    assert wrong.json()["detail"] == unknown.json()["detail"]


async def test_me_requires_auth(client: AsyncClient) -> None:
    assert (await client.get(f"{A}/me")).status_code == 401


async def test_progressive_lockout(app: FastAPI, client: AsyncClient) -> None:
    email = await register_and_login(client)
    async with build_client(app) as anon:
        for _ in range(5):
            r = await anon.post(f"{A}/login", json={"email": email, "password": "wrong-password-1"})
            assert r.status_code == 401
        # Correct password is now refused while locked.
        r = await anon.post(f"{A}/login", json={"email": email, "password": PASSWORD})
        assert r.status_code == 401


async def test_refresh_rotates_and_reuse_revokes_family(app: FastAPI, client: AsyncClient) -> None:
    await register_and_login(client)
    old_refresh = client.cookies.get("refresh")
    assert old_refresh
    r = await client.post(f"{A}/refresh")
    assert r.status_code == 204
    new_refresh = client.cookies.get("refresh")
    assert new_refresh and new_refresh != old_refresh

    # Attacker replays the old (already used) token.
    async with build_client(app) as attacker:
        attacker.cookies.set("refresh", old_refresh, path="/api/v1/auth")
        attacker.cookies.set("csrf", "x" * 20)
        r = await attacker.post(f"{A}/refresh")
        assert r.status_code == 401

    # The legitimate (newer) token in the same family is now dead too.
    r = await client.post(f"{A}/refresh")
    assert r.status_code == 401


async def test_logout_revokes_refresh(app: FastAPI, client: AsyncClient) -> None:
    await register_and_login(client)
    stolen = client.cookies.get("refresh")
    assert stolen
    assert (await client.post(f"{A}/logout")).status_code == 204
    async with build_client(app) as other:
        other.cookies.set("refresh", stolen, path="/api/v1/auth")
        other.cookies.set("csrf", "y" * 20)
        assert (await other.post(f"{A}/refresh")).status_code == 401


async def test_csrf_required_for_authenticated_writes(app: FastAPI) -> None:
    async with build_client(app, auto_csrf=False) as c:
        email = _email()
        await c.post(f"{A}/signup", json={"email": email, "password": PASSWORD})
        await c.post(f"{A}/login", json={"email": email, "password": PASSWORD})
        r = await c.post(f"{A}/logout")
        assert r.status_code == 403 and r.json()["code"] == "csrf_failed"
        r = await c.post(f"{A}/logout", headers={"x-csrf-token": "wrong"})
        assert r.status_code == 403
        r = await c.post(f"{A}/logout", headers={"x-csrf-token": c.cookies.get("csrf") or ""})
        assert r.status_code == 204


async def test_foreign_origin_rejected(client: AsyncClient) -> None:
    r = await client.post(
        f"{A}/login",
        json={"email": _email(), "password": "whatever-123456"},
        headers={"origin": "https://evil.example"},
    )
    assert r.status_code == 403 and r.json()["code"] == "csrf_failed"


async def test_email_verification_single_use(client: AsyncClient, mailer: CapturingMailer) -> None:
    email = await register_and_login(client)
    assert (await client.get(f"{A}/me")).json()["email_verified"] is False
    token = mailer.token_for(email, "Verify")
    assert (await client.post(f"{A}/verify-email", json={"token": token})).status_code == 204
    assert (await client.get(f"{A}/me")).json()["email_verified"] is True
    assert (await client.post(f"{A}/verify-email", json={"token": token})).status_code == 400


async def test_password_reset_flow(
    app: FastAPI, client: AsyncClient, mailer: CapturingMailer
) -> None:
    email = await register_and_login(client)
    r = await client.post(f"{A}/password-reset/request", json={"email": email})
    assert r.status_code == 202
    # Unknown email gets the same answer and no mail.
    unknown = _email()
    r2 = await client.post(f"{A}/password-reset/request", json={"email": unknown})
    assert r2.status_code == 202 and r2.json() == r.json()
    assert not [m for m in mailer.sent if m[0] == unknown]

    token = mailer.token_for(email, "Reset")
    new_pw = "brand new passphrase"
    r = await client.post(
        f"{A}/password-reset/confirm", json={"token": token, "new_password": new_pw}
    )
    assert r.status_code == 204
    r = await client.post(
        f"{A}/password-reset/confirm", json={"token": token, "new_password": new_pw}
    )
    assert r.status_code == 400  # single use

    # Existing sessions were signed out; new password works, old does not.
    assert (await client.post(f"{A}/refresh")).status_code == 401
    async with build_client(app) as fresh:
        assert (
            await fresh.post(f"{A}/login", json={"email": email, "password": PASSWORD})
        ).status_code == 401
        assert (
            await fresh.post(f"{A}/login", json={"email": email, "password": new_pw})
        ).status_code == 204


async def test_login_is_rate_limited(app: FastAPI, client: AsyncClient) -> None:
    app.state.limiter = RateLimiter(enabled=True)
    email = _email()
    codes = []
    for _ in range(12):
        r = await client.post(f"{A}/login", json={"email": email, "password": "nope-nope-nope"})
        codes.append(r.status_code)
    assert codes[:10] == [401] * 10
    assert 429 in codes[10:]
    limited = next(
        r
        for r in [await client.post(f"{A}/login", json={"email": email, "password": "x"})]
        if r.status_code == 429
    )
    assert int(limited.headers["retry-after"]) >= 1
