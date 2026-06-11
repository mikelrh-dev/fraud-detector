"""Tests for FastAPI dependency injection."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials

from src.core.dependencies import get_current_user, require_role


def test_get_current_user_valid_token():
    """Valid JWT should return user_id and role."""
    from src.core.security import create_access_token

    token = create_access_token(user_id="user-123", role="analyst")
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    request = MagicMock(spec=Request)

    result = get_current_user(request=request, credentials=creds)
    assert result["user_id"] == "user-123"
    assert result["role"] == "analyst"


def test_get_current_user_no_credentials():
    """Missing credentials should raise 401."""
    request = MagicMock(spec=Request)
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(request=request, credentials=None)
    assert exc_info.value.status_code == 401


def test_get_current_user_invalid_token():
    """Invalid token should raise 401."""
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials="bad.token.here")
    request = MagicMock(spec=Request)
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(request=request, credentials=creds)
    assert exc_info.value.status_code == 401


def test_require_role_allows_correct_role():
    """require_role should allow users with matching role."""
    user = {"user_id": "user-123", "role": "admin"}
    dep = require_role("admin")
    result = dep(user)
    assert result is user


def test_require_role_blocks_wrong_role():
    """require_role should raise 403 for users without matching role."""
    user = {"user_id": "user-123", "role": "analyst"}
    dep = require_role("admin")
    with pytest.raises(HTTPException) as exc_info:
        dep(user)
    assert exc_info.value.status_code == 403
