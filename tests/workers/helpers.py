"""Shared async helpers for embedding-worker tests."""

import asyncio


def idle_xreadgroup(delay: float = 0.02):
    """Return an async ``xreadgroup`` stand-in that actually suspends.

    An ``AsyncMock`` returning ``[]`` completes without ever yielding to the
    event loop, so the worker's read loop spins hot and starves the recovery
    task (production blocks 1000 ms server-side instead). This stand-in sleeps
    briefly per call, mirroring that suspension.
    """

    async def readgroup(*args, **kwargs):
        await asyncio.sleep(delay)
        return []

    return readgroup
