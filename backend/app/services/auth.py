import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.deps import AuthContext, set_rls_user
from app.core.security import (
    create_access_token,
    hash_password,
    needs_rehash,
    new_csrf_token,
    new_opaque_token,
    parse_opaque_token,
    sha256_hex,
    verify_password,
)
from app.models import User
from app.repositories.tokens import EmailTokenRepository, RefreshTokenRepository
from app.repositories.users import UserRepository
from app.services.mailer import Mailer

MAX_FAILED_BEFORE_LOCK = 5
MAX_LOCK = timedelta(minutes=15)
EMAIL_TOKEN_TTL = timedelta(hours=1)
VERIFY_TTL = timedelta(days=2)


@dataclass(frozen=True)
class Session:
    user_id: uuid.UUID
    access: str
    refresh: str
    csrf: str


class AuthService:
    def __init__(self, session: AsyncSession, settings: Settings, mailer: Mailer) -> None:
        self.db, self.settings, self.mailer = session, settings, mailer
        self.users = UserRepository(session)

    async def _ctx(self, user_id: uuid.UUID) -> AuthContext:
        await set_rls_user(self.db, user_id)
        return AuthContext(user_id)

    # -- signup / email verification ------------------------------------------------------

    async def signup(self, email: str, password: str) -> None:
        """Always looks the same to the caller whether or not the email exists."""
        pw_hash = hash_password(password)
        existing = await self.users.get_by_email(email)
        if existing is not None:
            await self.mailer.send(
                email,
                "Sign-up attempt",
                "An account already exists for this address. Log in instead.",
            )
            return
        try:
            async with self.db.begin_nested():
                user = await self.users.create(email, pw_hash)
        except IntegrityError:  # concurrent signup with same email
            return
        if self.settings.email_verification_required:
            await self._send_verification(user)
        else:
            user.email_verified = True

    async def _send_verification(self, user: User) -> None:
        ctx = await self._ctx(user.id)
        raw = new_opaque_token(user.id)
        await EmailTokenRepository(self.db, ctx).add(
            "verify", sha256_hex(raw), datetime.now(UTC) + VERIFY_TTL
        )
        link = f"{self.settings.frontend_base_url}/verify-email?token={raw}"
        await self.mailer.send(user.email, "Verify your email", f"Verify: {link}")

    async def verify_email(self, token: str) -> bool:
        user_id = parse_opaque_token(token)
        if user_id is None:
            return False
        ctx = await self._ctx(user_id)
        if not await EmailTokenRepository(self.db, ctx).consume("verify", sha256_hex(token)):
            return False
        user = await self.users.get_by_id(user_id)
        if user is not None:
            user.email_verified = True
        return True

    # -- login / sessions -----------------------------------------------------------------

    async def _issue(self, user_id: uuid.UUID, family_id: uuid.UUID) -> Session:
        ctx = await self._ctx(user_id)
        raw_refresh = new_opaque_token(user_id)
        await RefreshTokenRepository(self.db, ctx).add(
            family_id,
            sha256_hex(raw_refresh),
            datetime.now(UTC) + timedelta(days=self.settings.refresh_token_ttl_days),
        )
        access = create_access_token(
            user_id, self.settings.secret_key, self.settings.access_token_ttl_minutes
        )
        return Session(user_id, access, raw_refresh, new_csrf_token())

    async def login(self, email: str, password: str) -> Session | None:
        """Returns None on any failure (caller must still commit: failure counters persist)."""
        user = await self.users.get_by_email(email)
        now = datetime.now(UTC)
        locked = user is not None and user.locked_until is not None and user.locked_until > now
        ok = verify_password(user.password_hash if user else None, password)  # constant-ish time
        if user is None or locked:
            return None
        if not ok:
            user.failed_logins += 1
            if user.failed_logins >= MAX_FAILED_BEFORE_LOCK:
                delay = min(
                    MAX_LOCK, timedelta(minutes=2 ** (user.failed_logins - MAX_FAILED_BEFORE_LOCK))
                )
                user.locked_until = now + delay
            return None
        user.failed_logins = 0
        user.locked_until = None
        if user.password_hash and needs_rehash(user.password_hash):
            user.password_hash = hash_password(password)
        return await self._issue(user.id, uuid.uuid4())

    async def refresh(self, raw_refresh: str) -> Session | None:
        """Rotate. Reuse of a consumed token revokes the entire family (caller must commit)."""
        user_id = parse_opaque_token(raw_refresh)
        if user_id is None:
            return None
        ctx = await self._ctx(user_id)
        repo = RefreshTokenRepository(self.db, ctx)
        row = await repo.get_by_hash(sha256_hex(raw_refresh))
        if row is None:
            return None
        now = datetime.now(UTC)
        if row.used_at is not None or row.revoked_at is not None:
            await repo.revoke_family(row.family_id)
            return None
        if row.expires_at <= now:
            return None
        row.used_at = now
        return await self._issue(user_id, row.family_id)

    async def logout(self, raw_refresh: str | None) -> None:
        user_id = parse_opaque_token(raw_refresh) if raw_refresh else None
        if raw_refresh is None or user_id is None:
            return
        ctx = await self._ctx(user_id)
        repo = RefreshTokenRepository(self.db, ctx)
        row = await repo.get_by_hash(sha256_hex(raw_refresh))
        if row is not None:
            await repo.revoke_family(row.family_id)

    # -- password reset -------------------------------------------------------------------

    async def request_password_reset(self, email: str) -> None:
        user = await self.users.get_by_email(email)
        if user is None:
            return
        ctx = await self._ctx(user.id)
        raw = new_opaque_token(user.id)
        await EmailTokenRepository(self.db, ctx).add(
            "reset", sha256_hex(raw), datetime.now(UTC) + EMAIL_TOKEN_TTL
        )
        link = f"{self.settings.frontend_base_url}/reset-password?token={raw}"
        await self.mailer.send(user.email, "Reset your password", f"Reset: {link}")

    async def confirm_password_reset(self, token: str, new_password: str) -> bool:
        user_id = parse_opaque_token(token)
        if user_id is None:
            return False
        ctx = await self._ctx(user_id)
        if not await EmailTokenRepository(self.db, ctx).consume("reset", sha256_hex(token)):
            return False
        user = await self.users.get_by_id(user_id)
        if user is None:
            return False
        user.password_hash = hash_password(new_password)
        user.failed_logins = 0
        user.locked_until = None
        await RefreshTokenRepository(self.db, ctx).revoke_all()  # sign out everywhere
        return True
