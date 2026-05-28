"""Shared pytest fixtures.

Unit-tests on stage 0 don't need a real DB/Redis. The health endpoint is
exercised via dependency overrides that fake those subsystems, so the suite
can run in CI on SQLite-less, Redis-less hosts.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.v1 import health as health_module
from app.database import get_db
from app.main import app


class _StubSession:
    """Minimal stand-in for AsyncSession used by health-check unit tests."""

    async def execute(self, *_args: Any, **_kwargs: Any) -> Any:
        class _Result:
            def scalar(self) -> int:
                return 1

        return _Result()


async def _override_get_db() -> AsyncIterator[_StubSession]:
    yield _StubSession()


@pytest.fixture
def stub_db_and_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace DB session + Redis ping with always-ok stubs."""
    app.dependency_overrides[get_db] = _override_get_db

    async def _ok_redis() -> bool:
        return True

    monkeypatch.setattr(health_module, "_check_redis", _ok_redis)
    yield
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
async def client(stub_db_and_redis: None) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
