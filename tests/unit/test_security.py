"""Tests for JWT and password security utilities."""

from datetime import datetime, timedelta, timezone

import pytest
from jose import JWTError, jwt as jose_jwt

from src.core.config import settings
from src.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_hash_password_returns_bcrypt_hash():
    """Password hashing should return a bcrypt hash string."""
    hashed = hash_password("secure_password_123")
    assert hashed.startswith("$2b$") or hashed.startswith("$2a$")
    assert len(hashed) > 50


def test_verify_password_correct():
    """Verifying a correct password should return True."""
    hashed = hash_password("secure_password_123")
    assert verify_password("secure_password_123", hashed) is True


def test_verify_password_incorrect():
    """Verifying an incorrect password should return False."""
    hashed = hash_password("secure_password_123")
    assert verify_password("wrong_password", hashed) is False


def test_create_access_token_contains_claims():
    """Access token should contain sub, role, exp, and iat claims."""
    token = create_access_token(
        user_id="user-123",
        role="analyst",
    )
    payload = decode_access_token(token)
    assert payload["sub"] == "user-123"
    assert payload["role"] == "analyst"
    assert "exp" in payload
    assert "iat" in payload


def test_token_default_expiration():
    """Token created with default expiration should be valid."""
    token = create_access_token(
        user_id="user-123",
        role="admin",
        expires_delta=timedelta(minutes=15),
    )
    payload = decode_access_token(token)
    assert payload["sub"] == "user-123"


def test_expired_token_raises():
    """Decoding an expired token should raise JWTError."""
    payload = {
        "sub": "user-123",
        "role": "admin",
        "iat": datetime.now(tz=timezone.utc) - timedelta(hours=2),
        "exp": datetime.now(tz=timezone.utc) - timedelta(hours=1),
    }
    token = jose_jwt.encode(
        payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )
    with pytest.raises(JWTError):
        decode_access_token(token)


def test_decode_invalid_token_raises():
    """Decoding a tampered token should raise JWTError."""
    with pytest.raises(JWTError):
        decode_access_token("invalid.token.here")
