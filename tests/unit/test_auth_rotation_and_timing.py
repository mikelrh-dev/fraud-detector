"""A2 and A5: refresh-token rotation atomicity and login timing.

A2 — rotation used ``is_token_blacklisted()`` then ``blacklist_token()``: two
awaits with an event-loop yield between them. N concurrent replays of the same
refresh token all observed "not blacklisted" and all minted a fresh pair. The
blacklist was a record of revokes, never a guard against a race.

A5 — login raised before calling ``verify_password`` when the email was unknown,
so "no such account" returned in ~1 ms and "wrong password" in ~300 ms of
bcrypt. That is a reliable account-enumeration oracle.

The module-level ``pytestmark`` only applies to coroutine tests, so the pure
CPU tests below are sync and the request-level ones are async.
"""

import asyncio
import unittest.mock
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from httpx import AsyncClient

from src.core.security import (
    burn_password_verification,
    consume_token_once,
    create_refresh_token,
    hash_password,
    verify_password,
)


class TestConsumeTokenOnce:
    """A2: the atomic primitive."""

    @pytest.mark.asyncio

    async def test_first_caller_wins(self) -> None:
        redis = MagicMock()
        redis.set = AsyncMock(return_value="OK")

        assert await consume_token_once(redis, "jti-1", 900) is True

    @pytest.mark.asyncio

    async def test_second_caller_loses(self) -> None:
        """SET NX returns None when the key exists, which must mean 'already used'."""
        redis = MagicMock()
        redis.set = AsyncMock(return_value=None)

        assert await consume_token_once(redis, "jti-1", 900) is False

    @pytest.mark.asyncio

    async def test_uses_nx_with_a_ttl(self) -> None:
        """A plain SETEX would not be atomic and would resurrect the A2 race."""
        redis = MagicMock()
        redis.set = AsyncMock(return_value="OK")

        await consume_token_once(redis, "jti-1", 900)

        redis.set.assert_awaited_once_with(
            "token_blacklist:jti-1", "1", nx=True, ex=900
        )

    @pytest.mark.asyncio

    async def test_concurrent_replays_produce_exactly_one_winner(self) -> None:
        """The actual race: many callers, one claim.

        Simulates Redis SET NX semantics with a real dict, which is what a
        single-threaded event loop over an atomic Redis command amounts to.
        """
        store: dict[str, str] = {}

        async def set_redis(key: str, value: str, nx: bool = False, ex: int = 0):
            if nx and key in store:
                return None
            store[key] = value
            return "OK"

        redis = MagicMock()
        redis.set = set_redis

        results = await asyncio.gather(
            *(consume_token_once(redis, "jti-race", 900) for _ in range(25))
        )

        assert sum(results) == 1, (
            "exactly one caller may consume a single-use token; the rest must "
            "be refused or a replay mints extra token pairs"
        )


class TestRefreshRotationIsAtomic:
    """A2 end to end: concurrent refreshes of one token."""

    @pytest.mark.asyncio

    async def test_concurrent_refresh_yields_one_pair(
        self, test_client: AsyncClient, mock_db: AsyncMock, mock_user_row
    ) -> None:
        store: dict[str, str] = {}

        async def set_redis(key: str, value: str, nx: bool = False, ex: int = 0):
            if nx and key in store:
                return None
            store[key] = value
            return "OK"

        fake_redis = MagicMock()
        fake_redis.set = set_redis
        fake_redis.setex = AsyncMock()
        fake_redis.exists = AsyncMock(side_effect=lambda k: 1 if k in store else 0)
        fake_redis.incr = AsyncMock(return_value=1)
        fake_redis.expire = AsyncMock()

        from src.api.main import app
        from src.core.dependencies import get_redis

        async def _override():
            yield fake_redis

        app.dependency_overrides[get_redis] = _override
        try:
            user_id = str(uuid4())
            mock_user_row(mock_db, user_id, role="analyst")
            token = create_refresh_token(user_id=user_id, role="analyst")
            headers = {"Authorization": f"Bearer {token}"}

            responses = await asyncio.gather(
                *(test_client.post("/api/v1/auth/refresh", headers=headers) for _ in range(8))
            )
        finally:
            app.dependency_overrides.pop(get_redis, None)

        codes = [r.status_code for r in responses]
        assert codes.count(200) == 1, (
            f"exactly one refresh may succeed, got {codes}"
        )
        assert all(c in (200, 401) for c in codes), f"unexpected codes: {codes}"

    @pytest.mark.asyncio

    async def test_replay_after_success_is_refused(
        self, test_client: AsyncClient, mock_db: AsyncMock, mock_user_row
    ) -> None:
        from src.api.main import app
        from src.core.dependencies import get_redis

        store: dict[str, str] = {}

        async def set_redis(key: str, value: str, nx: bool = False, ex: int = 0):
            if nx and key in store:
                return None
            store[key] = value
            return "OK"

        fake_redis = MagicMock()
        fake_redis.set = set_redis
        fake_redis.setex = AsyncMock()
        fake_redis.exists = AsyncMock(side_effect=lambda k: 1 if k in store else 0)
        fake_redis.incr = AsyncMock(return_value=1)
        fake_redis.expire = AsyncMock()

        async def _override():
            yield fake_redis

        app.dependency_overrides[get_redis] = _override
        try:
            user_id = str(uuid4())
            mock_user_row(mock_db, user_id, role="analyst")
            token = create_refresh_token(user_id=user_id, role="analyst")
            headers = {"Authorization": f"Bearer {token}"}

            first = await test_client.post("/api/v1/auth/refresh", headers=headers)
            second = await test_client.post("/api/v1/auth/refresh", headers=headers)
        finally:
            app.dependency_overrides.pop(get_redis, None)

        assert first.status_code == 200
        assert second.status_code == 401


class TestLoginTimingOracle:
    """A5: an unknown account must cost the same as a wrong password."""

    def test_dummy_hash_is_a_real_bcrypt_hash(self) -> None:
        """A placeholder string would short-circuit and restore the oracle."""
        from src.core.security import _DUMMY_HASH

        assert _DUMMY_HASH.startswith("$2")
        assert len(_DUMMY_HASH) > 50

    def test_burn_does_not_raise(self) -> None:
        assert burn_password_verification("anything") is None

    def test_burn_accepts_a_wrong_password(self) -> None:
        assert burn_password_verification("not-the-dummy-plaintext") is None

    def test_burn_never_matches_a_real_account(self) -> None:
        """No password may verify against the dummy hash."""
        from src.core.security import _DUMMY_HASH

        for candidate in ("password", "admin", "", "123456"):
            assert not verify_password(candidate, _DUMMY_HASH)

    @pytest.mark.asyncio

    async def test_unknown_user_still_spends_bcrypt(
        self, test_client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        """The unknown-email branch must call the burn, not skip verification."""
        with unittest.mock.patch(
            "src.services.auth.burn_password_verification"
        ) as burn:
            result = MagicMock()
            result.scalar_one_or_none.return_value = None
            mock_db.execute = AsyncMock(return_value=result)

            response = await test_client.post(
                "/api/v1/auth/login",
                json={"email": "nobody@example.com", "password": "whatever"},
            )

        assert response.status_code in (401, 400)
        burn.assert_called_once()
        assert burn.call_args[0][0] == "whatever", (
            "the burn must verify the password the caller actually sent, "
            "otherwise the work is not comparable"
        )

    @pytest.mark.asyncio

    async def test_wrong_password_also_verifies_once(
        self, test_client: AsyncClient, mock_db: AsyncMock
    ) -> None:
        """Both branches must do exactly one bcrypt verification."""
        user = MagicMock()
        user.id = str(uuid4())
        user.role = MagicMock()
        user.role.value = "analyst"
        user.is_active = True
        user.hashed_password = hash_password("correct-password")
        result = MagicMock()
        result.scalar_one_or_none.return_value = user
        mock_db.execute = AsyncMock(return_value=result)

        with unittest.mock.patch(
            "src.services.auth.verify_password", return_value=False
        ) as verify:
            await test_client.post(
                "/api/v1/auth/login",
                json={"email": "real@example.com", "password": "wrong-password"},
            )

        verify.assert_called_once()
