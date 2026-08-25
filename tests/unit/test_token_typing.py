"""Token typing tests — R1-004 (audit wave 2).

Access and refresh tokens must be cryptographically distinguishable via a
``typ`` claim. A stolen access token must NOT be able to hit /auth/refresh,
and a refresh token must NOT be usable as an access token on protected
endpoints.
"""

import pytest
from jose import JWTError
from jose import jwt as pyjwt

from src.core.config import settings
from src.core.security import (
    create_access_token,
    create_refresh_token,
    decode_access_token,
)


def _decode(token: str) -> dict:
    return pyjwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )


class TestTokenClaims:
    """Tokens carry a typ claim identifying their role."""

    def test_access_token_has_typ_access(self):
        token = create_access_token(user_id="u1", role="analyst")
        assert _decode(token)["typ"] == "access"

    def test_refresh_token_has_typ_refresh(self):
        token = create_refresh_token(user_id="u1", role="analyst")
        assert _decode(token)["typ"] == "refresh"

    def test_refresh_token_longer_expiry_than_access(self):
        access = create_access_token(user_id="u1", role="analyst")
        refresh = create_refresh_token(user_id="u1", role="analyst")
        assert _decode(refresh)["exp"] > _decode(access)["exp"]


class TestAccessDecodeRejectsRefresh:
    """decode_access_token must refuse tokens whose typ is not 'access'."""

    def test_decode_rejects_refresh_token(self):
        refresh = create_refresh_token(user_id="u1", role="analyst")
        with pytest.raises(JWTError):
            decode_access_token(refresh)

    def test_decode_accepts_access_token(self):
        access = create_access_token(user_id="u1", role="analyst")
        payload = decode_access_token(access)
        assert payload["sub"] == "u1"
