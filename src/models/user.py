"""User ORM model."""

import enum

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import BaseModel


class UserRole(str, enum.Enum):
    """User role enumeration."""

    ADMIN = "admin"
    ANALYST = "analyst"


class User(BaseModel):
    """User account for authentication and authorization."""

    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        String(20),
        default=UserRole.ANALYST,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
