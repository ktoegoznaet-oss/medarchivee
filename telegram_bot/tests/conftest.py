"""Test harness for the telegram bot.

SQLite в памяти + копия моделей: один и тот же `Base.metadata` создаётся
из `db.models` через `create_all`, поэтому миграция backend здесь не
нужна — мы тестируем только bot-уровень.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from db.models import Base


@pytest.fixture
async def db_engine() -> AsyncIterator:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session_factory(
    db_engine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(db_engine, expire_on_commit=False)
