"""Pydantic schemas for authentication."""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    """Login credentials."""

    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1, max_length=255)


class RegisterRequest(BaseModel):
    """New user registration payload."""

    username: str = Field(..., min_length=3, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=255)
    role: str = Field(default="analyst", pattern=r"^(admin|analyst)$")


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
