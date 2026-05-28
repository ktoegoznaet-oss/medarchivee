"""Async SQLAlchemy engine + session factory for the bot.

Engine создаётся лениво (через `init_engine` или первый вызов
`session_factory`), а не на module-import: это позволяет в тестах
подменить URL, и не падать при импорте, если DB_HOST недоступен
(см. W10 в DIAGNOSTIC_REPORT.md).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from config import settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def init_engine(database_url: str | None = None) -> None:
    """Создать engine + session factory один раз.

    Вызывается из `bot.main()` после `_configure_logging()`, чтобы все
    стартовые ошибки писались в JSON-логи. Можно также подменить URL
    в тестах: `init_engine("sqlite+aiosqlite:///:memory:")`.
    """
    global _engine, _session_factory
    url = database_url or settings.database_url
    _engine = create_async_engine(url, echo=False, pool_pre_ping=True)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)


def session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        # Lazy fallback — если кто-то импортировал session_factory до init.
        init_engine()
    assert _session_factory is not None  # для mypy
    return _session_factory


async def get_session() -> AsyncIterator[AsyncSession]:
    async with session_factory()() as session:
        yield session
