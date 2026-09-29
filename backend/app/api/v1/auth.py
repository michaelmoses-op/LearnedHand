from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse

from app.core.cookies import clear_auth_cookies, cookie_names, set_auth_cookies
from app.core.deps import (
    AuthDep,
    DbDep,
    LimiterDep,
    MailerDep,
    SettingsDep,
    client_ip,
    csrf_protect,
    origin_check,
)
from app.core.errors import NotFoundError, problem
from app.repositories.users import UserRepository
from app.schemas.auth import (
    Accepted,
    Credentials,
    EmailRequest,
    LoginRequest,
    PasswordResetConfirm,
    TokenRequest,
    UserOut,
)
from app.services.auth import AuthService, Session

router = APIRouter(prefix="/auth", tags=["auth"])
public = [Depends(origin_check)]
authed = [Depends(csrf_protect)]


def _invalid_credentials(request: Request) -> JSONResponse:
    return problem(request, 401, "invalid_credentials", "Invalid email or password")


def _with_session(settings: SettingsDep, s: Session) -> Response:
    response = Response(status_code=204)
    set_auth_cookies(response, settings, s.access, s.refresh, s.csrf)
    return response


@router.post("/signup", status_code=202, response_model=Accepted, dependencies=public)
async def signup(
    body: Credentials,
    request: Request,
    db: DbDep,
    settings: SettingsDep,
    limiter: LimiterDep,
    mailer: MailerDep,
) -> Accepted:
    limiter.check(f"signup:ip:{client_ip(request)}", 10, 3600)
    await AuthService(db, settings, mailer).signup(body.email, body.password)
    await db.commit()
    return Accepted()


@router.post("/login", status_code=204, dependencies=public)
async def login(
    body: LoginRequest,
    request: Request,
    db: DbDep,
    settings: SettingsDep,
    limiter: LimiterDep,
    mailer: MailerDep,
) -> Response:
    limiter.check(f"login:ip:{client_ip(request)}", 30, 60)
    limiter.check(f"login:email:{body.email}", 10, 60)
    result = await AuthService(db, settings, mailer).login(body.email, body.password)
    await db.commit()  # persist failure counters / lockout as well as new sessions
    if result is None:
        return _invalid_credentials(request)
    return _with_session(settings, result)


@router.post("/refresh", status_code=204, dependencies=authed)
async def refresh(
    request: Request, db: DbDep, settings: SettingsDep, limiter: LimiterDep, mailer: MailerDep
) -> Response:
    limiter.check(f"refresh:ip:{client_ip(request)}", 60, 60)
    token = request.cookies.get(cookie_names(settings).refresh)
    result = await AuthService(db, settings, mailer).refresh(token) if token else None
    await db.commit()  # persists family revocation on token reuse
    if result is None:
        response = problem(request, 401, "unauthenticated", "Authentication required")
        clear_auth_cookies(response, settings)
        return response
    return _with_session(settings, result)


@router.post("/logout", status_code=204, dependencies=authed)
async def logout(request: Request, db: DbDep, settings: SettingsDep, mailer: MailerDep) -> Response:
    token = request.cookies.get(cookie_names(settings).refresh)
    await AuthService(db, settings, mailer).logout(token)
    await db.commit()
    response = Response(status_code=204)
    clear_auth_cookies(response, settings)
    return response


@router.get("/me", response_model=UserOut)
async def me(auth: AuthDep, db: DbDep) -> UserOut:
    user = await UserRepository(db).get_by_id(auth.user_id)
    if user is None:
        raise NotFoundError("User not found")
    return UserOut(id=user.id, email=user.email, email_verified=user.email_verified)


@router.post("/verify-email", status_code=204, dependencies=public)
async def verify_email(
    body: TokenRequest, db: DbDep, settings: SettingsDep, mailer: MailerDep, request: Request
) -> Response:
    ok = await AuthService(db, settings, mailer).verify_email(body.token)
    await db.commit()
    if not ok:
        return problem(request, 400, "invalid_token", "Invalid or expired token")
    return Response(status_code=204)


@router.post(
    "/password-reset/request", status_code=202, response_model=Accepted, dependencies=public
)
async def password_reset_request(
    body: EmailRequest,
    request: Request,
    db: DbDep,
    settings: SettingsDep,
    limiter: LimiterDep,
    mailer: MailerDep,
) -> Accepted:
    limiter.check(f"reset:ip:{client_ip(request)}", 5, 3600)
    limiter.check(f"reset:email:{body.email}", 3, 3600)
    await AuthService(db, settings, mailer).request_password_reset(body.email)
    await db.commit()
    return Accepted()


@router.post("/password-reset/confirm", status_code=204, dependencies=public)
async def password_reset_confirm(
    body: PasswordResetConfirm,
    request: Request,
    db: DbDep,
    settings: SettingsDep,
    limiter: LimiterDep,
    mailer: MailerDep,
) -> Response:
    limiter.check(f"reset-confirm:ip:{client_ip(request)}", 10, 3600)
    ok = await AuthService(db, settings, mailer).confirm_password_reset(
        body.token, body.new_password
    )
    await db.commit()
    if not ok:
        return problem(request, 400, "invalid_token", "Invalid or expired token")
    return Response(status_code=204)
