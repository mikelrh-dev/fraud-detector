"""Tests for Pydantic schemas."""

import uuid

import pytest
from pydantic import ValidationError

from src.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)


class TestAuthSchemas:
    """Auth schema validation tests."""

    def test_login_request_valid(self):
        """LoginRequest should accept valid username and password."""
        data = LoginRequest(username="analyst1", password="secure_pass_123")
        assert data.username == "analyst1"
        assert data.password == "secure_pass_123"

    def test_login_request_empty_username_raises(self):
        """LoginRequest with empty username should fail validation."""
        with pytest.raises(ValidationError):
            LoginRequest(username="", password="secure_pass_123")

    def test_login_request_empty_password_raises(self):
        """LoginRequest with empty password should fail validation."""
        with pytest.raises(ValidationError):
            LoginRequest(username="analyst1", password="")

    def test_register_request_valid(self):
        """RegisterRequest should accept valid user data."""
        data = RegisterRequest(
            username="new_analyst",
            email="analyst@example.com",
            password="secure_pass_123",
            role="analyst",
        )
        assert data.username == "new_analyst"
        assert data.email == "analyst@example.com"

    def test_register_request_invalid_email_raises(self):
        """RegisterRequest with invalid email should fail validation."""
        with pytest.raises(ValidationError):
            RegisterRequest(
                username="new_analyst",
                email="not-an-email",
                password="secure_pass_123",
                role="analyst",
            )

    def test_register_request_invalid_role_raises(self):
        """RegisterRequest with invalid role should fail validation."""
        with pytest.raises(ValidationError):
            RegisterRequest(
                username="new_analyst",
                email="analyst@example.com",
                password="secure_pass_123",
                role="superadmin",
            )

    def test_token_response_valid(self):
        """TokenResponse should accept valid token data."""
        data = TokenResponse(
            access_token="eyJ...",
            refresh_token="eyJ...",
            token_type="bearer",
        )
        assert data.access_token == "eyJ..."
        assert data.token_type == "bearer"

    def test_token_response_default_type(self):
        """TokenResponse should default token_type to 'bearer'."""
        data = TokenResponse(
            access_token="eyJ...",
            refresh_token="eyJ...",
        )
        assert data.token_type == "bearer"

    def test_user_response_valid(self):
        """UserResponse should accept valid user data."""
        user_id = uuid.uuid4()
        data = UserResponse(
            id=user_id,
            username="analyst1",
            email="analyst@example.com",
            role="analyst",
            is_active=True,
        )
        assert data.id == user_id
        assert data.role == "analyst"
        assert data.is_active is True
