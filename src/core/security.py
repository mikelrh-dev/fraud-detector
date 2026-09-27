"""JWT token management and password hashing utilities."""

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from jose import JWTError, jwt  # type: ignore[import-untyped]
from passlib.context import CryptContext  # type: ignore[import-untyped]
from redis.asyncio import Redis

from src.core.config import settings

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a plaintext password using bcrypt."""
    return _pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against its bcrypt hash."""
    return _pwd_context.verify(plain_password, hashed_password)


# A5: a pre-computed bcrypt hash of a value no user can present, used to burn
# the same CPU when the account does not exist.
#
# The login path used to raise before calling verify_password when the email was
# unknown, so "user does not exist" returned in ~1 ms and "wrong password" took
# ~300 ms of bcrypt. That gap is a reliable account-enumeration oracle: an
# attacker measures, never guesses.
#
# The hash must be a real bcrypt hash, not a dummy string, or verify_password
# short-circuits and the timing is identical to the fast path again. It is
# generated at import from a fixed random value, so the plaintext is never a
# guessable constant and no password is ever compared against it successfully.
_DUMMY_HASH = _pwd_context.hash(secrets.token_urlsafe(32))


def burn_password_verification(plain_password: str) -> None:
    """Spend the same CPU as a real verification. Always returns False.

    Call this on the "account does not exist" branch so it is indistinguishable
    in timing from a wrong password. The result is deliberately discarded: a
    real user must never match this hash.
    """
    try:
        _pwd_context.verify(plain_password, _DUMMY_HASH)
    except Exception:
        # verify() can raise on a malformed input; the CPU has been spent
        # either way, which is the entire point of the call.
        pass
    return None


def create_access_token(
    user_id: str,
    role: str,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a JWT access token with user_id, role, and typ claims."""
    delta = expires_delta or timedelta(minutes=settings.jwt_exp_minutes)
    return _encode_token(user_id=user_id, role=role, typ="access", delta=delta)


def create_refresh_token(
    user_id: str,
    role: str,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a JWT refresh token (typ='refresh') with a longer lifetime.

    A refresh token is only valid at /auth/refresh; it is rejected as an
    access token everywhere else (R1-004).
    """
    delta = expires_delta or timedelta(minutes=settings.jwt_refresh_exp_minutes)
    return _encode_token(user_id=user_id, role=role, typ="refresh", delta=delta)


def _encode_token(user_id: str, role: str, typ: str, delta: timedelta) -> str:
    now = datetime.now(tz=timezone.utc)
    payload: dict[str, Any] = {
        "sub": user_id,
        "role": role,
        "typ": typ,
        # Unique token ID: enables real revocation (R1-002) and makes
        # refresh rotation meaningful even within the same second.
        "jti": str(uuid4()),
        "iat": now,
        "exp": now + delta,
    }
    return jwt.encode(
        payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )


def _decode_token(token: str, expected_typ: str) -> dict[str, Any]:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            options={"verify_exp": True},
        )
    except JWTError:
        raise
    if payload.get("typ") != expected_typ:
        raise JWTError(f"Invalid token type: expected {expected_typ}")
    return payload


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate an access token.

    Raises JWTError if the token is invalid, expired, or not an access token.
    """
    return _decode_token(token, expected_typ="access")


def decode_refresh_token(token: str) -> dict[str, Any]:
    """Decode and validate a refresh token.

    Raises JWTError if the token is invalid, expired, or not a refresh token.
    """
    return _decode_token(token, expected_typ="refresh")


async def is_token_blacklisted(redis_client: Redis, jti: str) -> bool:
    """Check if a token has been blacklisted in Redis."""
    return await redis_client.exists(f"token_blacklist:{jti}") > 0


async def blacklist_token(redis_client: Redis, jti: str, ttl: int = 900) -> None:
    """Add a token to the Redis blacklist with a TTL matching token expiry."""
    await redis_client.setex(f"token_blacklist:{jti}", ttl, "1")


async def consume_token_once(redis_client: Redis, jti: str, ttl: int) -> bool:
    """Atomically claim a single-use token. Returns True only for the first caller.

    A2: rotation used to be two separate awaits — ``is_token_blacklisted`` then
    ``blacklist_token``. Between them the event loop can yield, so N concurrent
    replays of the same refresh token all observed "not blacklisted" and all
    proceeded to mint a fresh pair. The blacklist is only a *record* of revokes;
    it never *prevented* a race.

    ``SET key value NX EX ttl`` is the fix: Redis executes it as a single
    command, so exactly one caller can create the key. The losers get ``None``
    back and must treat the token as already consumed.

    Deliberately not a Lua script. The atomicity guarantee needed here is
    per-key, and ``SET NX EX`` already provides it inside one Redis command, so
    a script would add a second failure mode (script cache, ACL) for nothing.

    Returns True when this caller won the claim and must proceed.
    """
    claimed = await redis_client.set(f"token_blacklist:{jti}", "1", nx=True, ex=ttl)
    return bool(claimed)
