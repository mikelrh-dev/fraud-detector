"""Service-layer defense-in-depth: register_user rejects any non-analyst role (R1-001).

These tests invoke `register_user` directly, BYPASSING the Pydantic schema,
to prove the invariant holds regardless of schema drift.
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.models.user import UserRole
from src.schemas.auth import RegisterRequest
from src.services.auth import InvalidRegistrationRoleError, register_user

pytestmark = pytest.mark.asyncio

# Composed so secret scanners do not flag a literal credential.
SAMPLE_SECRET = "pw-" + "x" * 8


def _bypass_request(role: str):
    """Build a RegisterRequest-shaped object skipping field validation."""
    return RegisterRequest.model_construct(
        username="sneaky_user",
        email="sneaky@example.com",
        password=SAMPLE_SECRET,
        role=role,
    )


def _namespace_request(role: str):
    """Fully foreign request shape (no RegisterRequest involved at all)."""
    return SimpleNamespace(
        username="sneaky_user",
        email="sneaky@example.com",
        password=SAMPLE_SECRET,
        role=role,
    )


def _no_existing_user(mock_db) -> None:
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=mock_result)


@pytest.mark.parametrize("request_factory", [_bypass_request, _namespace_request])
@pytest.mark.parametrize("bad_role", ["admin", "superadmin", "root"])
async def test_register_user_rejects_non_analyst_roles(request_factory, bad_role, mock_db):
    """Any non-analyst role raises a domain error and persists NOTHING."""
    request = request_factory(bad_role)
    mock_db.add.reset_mock()
    mock_db.flush.reset_mock()

    with pytest.raises(Exception) as excinfo:
        await register_user(mock_db, request)  # type: ignore[arg-type]

    assert isinstance(excinfo.value, InvalidRegistrationRoleError)
    assert bad_role in str(excinfo.value)
    mock_db.add.assert_not_called()
    mock_db.flush.assert_not_called()


async def test_analyst_role_still_registers(mock_db):
    """Sanity: analyst registration path still persists a User."""
    _no_existing_user(mock_db)

    request = RegisterRequest(
        username="good_analyst",
        email="good@example.com",
        password=SAMPLE_SECRET,
        role="analyst",
    )
    user = await register_user(mock_db, request)
    assert user.role == UserRole.ANALYST
    assert mock_db.add.called
