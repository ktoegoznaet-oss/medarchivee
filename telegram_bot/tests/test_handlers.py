"""Bot-side tests: тексты + минимальная логика привязки.

Aiogram-dispatcher feed_update — слишком много обвязки (User, Chat,
Update, Message, токен бота). Поэтому проверяем:
  * тексты в `handlers.texts` — они дисциплинированы, легко падают на регрессии;
  * data-access слой `db.binding` (он же — основа `/start КОД` и `/unbind`).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from db.binding import find_binding, try_bind, unbind
from db.models import TelegramBinding, TelegramBindingCode, User
from handlers.texts import (
    GREETING_WITH_INSTRUCTIONS,
    HELP_TEXT,
    bind_success_text,
)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


async def _seed_user_with_code(
    session_factory: async_sessionmaker, *, code: str, expires_in: timedelta
) -> int:
    async with session_factory() as session:
        user = User(email="u@example.com", username="u")
        session.add(user)
        await session.flush()
        session.add(
            TelegramBindingCode(
                user_id=user.id,
                code=code,
                expires_at=_now() + expires_in,
            )
        )
        await session.commit()
        return user.id


# ---- Texts -------------------------------------------------------------- #


def test_greeting_contains_instructions() -> None:
    assert "Настройки → Telegram" in GREETING_WITH_INSTRUCTIONS
    assert "Чувствительные подробности" in GREETING_WITH_INSTRUCTIONS


def test_help_contains_disclaimer() -> None:
    assert "серверы Telegram" in HELP_TEXT
    assert "не передаются" in HELP_TEXT


def test_bind_success_uses_name() -> None:
    assert "Алиса" in bind_success_text("Алиса")
    assert "/help" in bind_success_text("Алиса")


# ---- Binding flow ------------------------------------------------------- #


@pytest.mark.asyncio
async def test_try_bind_with_valid_code_creates_binding(
    session_factory: async_sessionmaker,
) -> None:
    user_id = await _seed_user_with_code(
        session_factory, code="123456", expires_in=timedelta(minutes=10)
    )
    result = await try_bind(
        session_factory,
        code="123456",
        telegram_user_id=987654,
        telegram_username="@AliCE",
    )
    assert result.ok is True
    assert result.user_id == user_id
    binding = await find_binding(session_factory, 987654)
    assert binding is not None
    # username нормализован: без @, в нижнем регистре.
    assert binding.telegram_username == "alice"


@pytest.mark.asyncio
async def test_try_bind_with_expired_code_rejected(
    session_factory: async_sessionmaker,
) -> None:
    await _seed_user_with_code(
        session_factory, code="222222", expires_in=timedelta(minutes=-1)
    )
    result = await try_bind(
        session_factory,
        code="222222",
        telegram_user_id=111,
        telegram_username=None,
    )
    assert result.ok is False
    assert result.error == "code_expired"


@pytest.mark.asyncio
async def test_try_bind_with_garbage_code_format_rejected(
    session_factory: async_sessionmaker,
) -> None:
    result = await try_bind(
        session_factory,
        code="abc",
        telegram_user_id=111,
        telegram_username=None,
    )
    assert result.ok is False
    assert result.error == "invalid_code_format"


@pytest.mark.asyncio
async def test_try_bind_reuses_code_blocked(
    session_factory: async_sessionmaker,
) -> None:
    await _seed_user_with_code(
        session_factory, code="333333", expires_in=timedelta(minutes=10)
    )
    first = await try_bind(
        session_factory,
        code="333333",
        telegram_user_id=42,
        telegram_username=None,
    )
    assert first.ok is True
    second = await try_bind(
        session_factory,
        code="333333",
        telegram_user_id=43,
        telegram_username=None,
    )
    assert second.ok is False
    assert second.error == "invalid_code"


@pytest.mark.asyncio
async def test_unbind_removes_binding(
    session_factory: async_sessionmaker,
) -> None:
    await _seed_user_with_code(
        session_factory, code="555555", expires_in=timedelta(minutes=10)
    )
    await try_bind(
        session_factory,
        code="555555",
        telegram_user_id=77,
        telegram_username=None,
    )
    removed = await unbind(session_factory, 77)
    assert removed is True
    assert await find_binding(session_factory, 77) is None


@pytest.mark.asyncio
async def test_unbind_no_binding_returns_false(
    session_factory: async_sessionmaker,
) -> None:
    removed = await unbind(session_factory, 999)
    assert removed is False
