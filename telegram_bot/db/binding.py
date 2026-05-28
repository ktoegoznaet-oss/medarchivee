"""Bot-side data-access layer.

Кодом ниже бот:
  * ищет привязку по telegram_user_id (для /start без аргументов, /status, /today);
  * валидирует и применяет код привязки (/start КОД и deep-link);
  * удаляет привязку (/unbind).

Логика повторяет `backend/app/services/telegram_service.py` — намеренная
дубликация согласно подсказке 6.2. При расхождении источник истины —
backend (его источник миграций и API).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from db.models import TelegramBinding, TelegramBindingCode

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class BindResult:
    ok: bool
    error: str | None = None
    user_id: int | None = None


async def find_binding(
    session_factory: async_sessionmaker[AsyncSession], telegram_user_id: int
) -> TelegramBinding | None:
    async with session_factory() as session:
        return (
            await session.execute(
                select(TelegramBinding).where(
                    TelegramBinding.telegram_user_id == telegram_user_id
                )
            )
        ).scalar_one_or_none()


async def try_bind(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    code: str,
    telegram_user_id: int,
    telegram_username: str | None,
) -> BindResult:
    code_clean = (code or "").strip()
    if not code_clean.isdigit() or len(code_clean) != 6:
        return BindResult(ok=False, error="invalid_code_format")

    normalized_username = (
        telegram_username.lstrip("@").lower() if telegram_username else None
    )

    async with session_factory() as session:
        row = (
            await session.execute(
                select(TelegramBindingCode).where(
                    TelegramBindingCode.code == code_clean
                )
            )
        ).scalar_one_or_none()
        if row is None or row.used:
            return BindResult(ok=False, error="invalid_code")
        now = datetime.now(UTC).replace(tzinfo=None)
        if row.expires_at < now:
            return BindResult(ok=False, error="code_expired")

        existing = (
            await session.execute(
                select(TelegramBinding).where(
                    TelegramBinding.telegram_user_id == telegram_user_id
                )
            )
        ).scalar_one_or_none()
        if existing is not None and existing.user_id != row.user_id:
            return BindResult(ok=False, error="telegram_account_already_bound")

        own_binding = (
            await session.execute(
                select(TelegramBinding).where(
                    TelegramBinding.user_id == row.user_id
                )
            )
        ).scalar_one_or_none()
        if own_binding is not None:
            own_binding.telegram_user_id = telegram_user_id
            own_binding.telegram_username = normalized_username
        elif existing is not None:
            existing.telegram_username = normalized_username
        else:
            session.add(
                TelegramBinding(
                    user_id=row.user_id,
                    telegram_user_id=telegram_user_id,
                    telegram_username=normalized_username,
                )
            )
        row.used = True
        await session.commit()
        log.info(
            "telegram_bot.bound",
            user_id=row.user_id,
            telegram_user_id=telegram_user_id,
        )
        return BindResult(ok=True, user_id=row.user_id)


async def unbind(
    session_factory: async_sessionmaker[AsyncSession], telegram_user_id: int
) -> bool:
    async with session_factory() as session:
        binding = (
            await session.execute(
                select(TelegramBinding).where(
                    TelegramBinding.telegram_user_id == telegram_user_id
                )
            )
        ).scalar_one_or_none()
        if binding is None:
            return False
        user_id = binding.user_id
        await session.delete(binding)
        await session.execute(
            delete(TelegramBindingCode).where(
                TelegramBindingCode.user_id == user_id
            )
        )
        await session.commit()
        log.info("telegram_bot.unbound", user_id=user_id)
        return True
