"""Admin Telegram bot — отдельный долгоживущий процесс.

Запускается командой `python -m app.services.admin_telegram.bot` в
контейнере `admin_telegram_bot` из docker-compose.

Реагирует ТОЛЬКО на сообщения от TELEGRAM_ADMIN_CHAT_ID — это критично
для безопасности: иначе любой, кто узнает username бота, сможет дергать
/stats и /health. На уровне aiogram Filter — отсеиваем чужие чаты до
выполнения handler'ов.

Команды:
  /stats   — текущая статистика (users, активность, тикеты)
  /health  — статус сервера: uptime, RAM, диск, контейнеры
  /help    — список команд
"""

from __future__ import annotations

import asyncio
import logging
import os
import platform
import shutil
import time
from datetime import UTC, datetime

import structlog
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.models.support import SupportTicket
from app.models.user import User, UserStatus


_PROCESS_START = time.monotonic()


def _configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
    )


def _build_router(session_factory: async_sessionmaker[AsyncSession]) -> Router:
    """Создать router с привязкой к session_factory."""
    router = Router()
    log = structlog.get_logger("admin_telegram.handlers")

    # Filter: только наш chat_id. Любое другое сообщение полностью
    # игнорируется — мы даже не пишем «доступ запрещён», чтобы не
    # подтверждать существование бота посторонним.
    expected_chat_id = settings.telegram_admin_chat_id.strip()
    chat_filter = F.chat.id == int(expected_chat_id) if expected_chat_id else F.chat.id == -1

    @router.message(Command("help"), chat_filter)
    async def help_handler(message: Message) -> None:
        await message.answer(
            "<b>МедАрхив — Admin Bot</b>\n"
            "/stats — статистика по пользователям и тикетам\n"
            "/health — состояние сервера\n"
            "/help — это сообщение"
        )

    @router.message(Command("stats"), chat_filter)
    async def stats_handler(message: Message) -> None:
        async with session_factory() as db:
            users_total = (
                await db.execute(select(func.count(User.id)))
            ).scalar_one()
            users_blocked = (
                await db.execute(
                    select(func.count(User.id)).where(
                        User.status == UserStatus.BLOCKED
                    )
                )
            ).scalar_one()
            tickets_total = (
                await db.execute(select(func.count(SupportTicket.id)))
            ).scalar_one()
            tickets_new = (
                await db.execute(
                    select(func.count(SupportTicket.id)).where(
                        SupportTicket.status == "new"
                    )
                )
            ).scalar_one()
        log.info("admin_telegram.stats_requested", chat_id=message.chat.id)
        await message.answer(
            "<b>📊 Статистика</b>\n"
            f"Пользователей: <b>{users_total}</b> (заблокировано: {users_blocked})\n"
            f"Тикетов: <b>{tickets_total}</b> (новых: {tickets_new})"
        )

    @router.message(Command("health"), chat_filter)
    async def health_handler(message: Message) -> None:
        uptime_seconds = time.monotonic() - _PROCESS_START
        uptime_str = _fmt_seconds(uptime_seconds)
        total, used, free = shutil.disk_usage(settings.uploads_root or "/")
        disk_pct = (used / total) * 100 if total > 0 else 0
        await message.answer(
            "<b>🩺 Health</b>\n"
            f"Bot uptime: {uptime_str}\n"
            f"Python: {platform.python_version()}\n"
            f"Disk: {disk_pct:.1f}% used "
            f"({_fmt_bytes(used)} / {_fmt_bytes(total)})\n"
            f"Free: {_fmt_bytes(free)}\n"
            f"Server time (UTC): {datetime.now(UTC).isoformat(timespec='seconds')}"
        )

    return router


def _fmt_seconds(s: float) -> str:
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    return f"{h}ч {m}м" if h else f"{m}м"


def _fmt_bytes(b: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    v = float(b)
    i = 0
    while v >= 1024 and i < len(units) - 1:
        v /= 1024
        i += 1
    return f"{v:.1f} {units[i]}"


async def main() -> None:
    _configure_logging()
    log = structlog.get_logger("admin_telegram")

    if not settings.telegram_admin_bot_token:
        log.error("admin_telegram.missing_token")
        raise SystemExit(
            "TELEGRAM_ADMIN_BOT_TOKEN не задан. Подставь токен от @BotFather в .env."
        )
    if not settings.telegram_admin_chat_id:
        log.error("admin_telegram.missing_chat_id")
        raise SystemExit(
            "TELEGRAM_ADMIN_CHAT_ID не задан. Узнай свой chat_id через @userinfobot."
        )

    # SQLite-fallback для CI-смоук-тестов
    db_url = settings.database_url
    engine = create_async_engine(db_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    bot = Bot(
        token=settings.telegram_admin_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(_build_router(session_factory))

    log.info(
        "admin_telegram.starting",
        chat_id=settings.telegram_admin_chat_id,
        pid=os.getpid(),
    )
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
