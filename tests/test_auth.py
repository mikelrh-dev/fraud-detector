"""Auth tests — password hashing, JWT encode/decode, token expiration, blacklist.

These tests verify the core auth primitives used throughout the system.
"""

from datetime import datetime, timedelta, timezone

import pytest
from jose import JWTError, jwt as jose_jwt

from src.core.config import settings
from src.core.security import (
    blacklist_token,
    create_access_token,
    decode_access_token,
    hash_password,
    is_token_blacklisted,
    verify_password,
)


class TestPasswordHashing:
    """Password hashing and verification tests."""

    def test_hash_password_returns_hash(self):
        """Hash should be a bcrypt string."""
        hashed = hash_password("my_password")
        assert hashed.startswith("$2b$") or hashed.startswith("$2a$")
        assert len(hashed) > 50

    def test_verify_correct_password(self):
        """Correct password should verify."""
        hashed = hash_password("my_password")
        assert verify_password("my_password", hashed) is True

    def test_verify_wrong_password(self):
        """Wrong password should not verify."""
        hashed = hash_password("my_password")
        assert verify_password("wrong_password", hashed) is False

    def test_different_passwords_different_hashes(self):
        """Different passwords produce different hashes."""
        hash1 = hash_password("password_1")
        hash2 = hash_password("password_2")
        assert hash1 != hash2


class TestJWT:
    """JWT token creation and validation tests."""

    def test_create_token_contains_claims(self):
        """Token should include sub, role, exp, iat."""
        token = create_access_token(user_id="user-1", role="admin")
        payload = decode_access_token(token)
        assert payload["sub"] == "user-1"
        assert payload["role"] == "admin"
        assert "exp" in payload
        assert "iat" in payload

    def test_expired_token_rejected(self):
        """Expired token should raise JWTError."""
        past = datetime.now(tz=timezone.utc) - timedelta(hours=1)
        payload = {
            "sub": "user-1",
            "role": "analyst",
            "iat": past - timedelta(hours=1),
            "exp": past,
        }
        token = jose_jwt.encode(
            payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
        )
        with pytest.raises(JWTError):
            decode_access_token(token)

    def test_invalid_signature_rejected(self):
        """Token with wrong key should raise JWTError."""
        token = jose_jwt.encode(
            {"sub": "user-1", "role": "analyst"},
            "wrong-secret",
            algorithm="HS256",
        )
        with pytest.raises(JWTError):
            decode_access_token(token)

    def test_malformed_token_rejected(self):
        """Garbage token should raise JWTError."""
        with pytest.raises(JWTError):
            decode_access_token("not.a.token")


@pytest.mark.asyncio
class TestTokenBlacklist:
    """Token blacklist operations (requires Redis mock)."""

    async def test_is_token_blacklisted_false(self):
        """Fresh token should not be blacklisted."""
        from unittest.mock import AsyncMock

        redis = AsyncMock()
        redis.exists = AsyncMock(return_value=0)
        assert await is_token_blacklisted(redis, "some-jti") is False

    async def test_blacklist_token(self):
        """Blacklisting should store the token in Redis."""
        from unittest.mock import AsyncMock

        redis = AsyncMock()
        redis.setex = AsyncMock()
        await blacklist_token(redis, "some-jti", ttl=900)
        redis.setex.assert_called_once_with("token_blacklist:some-jti", 900, "1")

    async def test_blacklisted_token_detected(self):
        """Blacklisted token should return True."""
        from unittest.mock import AsyncMock

        redis = AsyncMock()
        redis.exists = AsyncMock(return_value=1)
        assert await is_token_blacklisted(redis, "some-jti") is True
