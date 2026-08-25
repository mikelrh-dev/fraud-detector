"""Pydantic schemas for authentication."""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, ValidationInfo, field_validator

# Common/weak passwords rejected at registration (English + Spanish-friendly).
COMMON_PASSWORDS = {
    "password",
    "12345678",
    "qwerty123",
    "admin123",
    "letmein",
    "123456",
    "welcome",
    "monkey",
    "1q2w3e4r",
    "abc123",
    "password123",
    "admin",
    "contraseña",
    "prueba",
    "demo",
    "común",
    "clave123",
}


class LoginRequest(BaseModel):
    """Login credentials."""

    email: EmailStr
    password: str = Field(..., min_length=1, max_length=255)


class RegisterRequest(BaseModel):
    """New user registration payload."""

    username: str = Field(
        ...,
        min_length=3,
        max_length=100,
        pattern=r"^[a-zA-Z0-9_.-]+$",  # letters, numbers, underscore, period, hyphen only
    )
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=64)  # bcrypt 72-byte limit
    role: str = Field(
        default="analyst", pattern=r"^analyst$"
    )  # self-service never grants admin (R1-001)

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str, info: ValidationInfo) -> str:
        """Enforce password policy (OWASP): no common passwords, no personal info."""
        # 1. Reject common/weak passwords
        if v.lower() in COMMON_PASSWORDS:
            raise ValueError("Esta contraseña es muy común. Elija una más segura.")

        # 2. Reject passwords derived from the email local part
        if "email" in info.data:
            email_local = info.data["email"].split("@")[0].lower()
            if email_local in v.lower():
                raise ValueError("La contraseña no puede contener partes del email.")

        # 3. Reject passwords derived from the username
        if "username" in info.data:
            username = info.data["username"].lower()
            if username in v.lower():
                raise ValueError(
                    "La contraseña no puede contener el nombre de usuario."
                )

        return v


class TokenResponse(BaseModel):
    """JWT token response."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    """Public user profile (excludes password)."""

    id: uuid.UUID
    username: str
    email: str
    role: str
    is_active: bool
    created_at: datetime | None = None
