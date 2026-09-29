import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

# argon2id; ~64 MiB, t=3, p=4 (OWASP-aligned). Parameters are embedded in each hash,
# so they can be raised later and hashes upgraded on login via needs_rehash.
_hasher = PasswordHasher(time_cost=3, memory_cost=64 * 1024, parallelism=4)
# Verified against when the email is unknown so response time doesn't reveal existence.
_DUMMY_HASH = _hasher.hash("dummy-password-for-timing")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def new_opaque_token(user_id: uuid.UUID) -> str:
    """`<user_id>.<secret>`. The user id prefix lets us set the RLS context before lookup;
    the secret is what is hashed and stored."""
    return f"{user_id}.{secrets.token_urlsafe(32)}"


def parse_opaque_token(token: str) -> uuid.UUID | None:
    prefix, sep, secret = token.partition(".")
    if not sep or not secret:
        return None
    try:
        return uuid.UUID(prefix)
    except ValueError:
        return None


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def create_access_token(user_id: uuid.UUID, secret: str, ttl_minutes: int) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": now,
        "exp": now + timedelta(minutes=ttl_minutes),
        "jti": uuid.uuid4().hex,
        "typ": "access",
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_access_token(token: str, secret: str) -> uuid.UUID | None:
    try:
        payload = jwt.decode(
            token, secret, algorithms=["HS256"], options={"require": ["exp", "sub"]}
        )
        if payload.get("typ") != "access":
            return None
        return uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, ValueError):
        return None
