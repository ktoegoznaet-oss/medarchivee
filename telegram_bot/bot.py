"""Telegram bot entrypoint — aiogram 3.x, long-polling.

Long-polling намеренно: на проде на этапе 12 переключим на webhook
через nginx; для dev/staging long-polling проще (не нужен публичный
домен и HTTPS).
"""

from __future__ import annotations

import asyncio
import logging

import structlog
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import settings
from db.session import init_engine
from handlers import help as help_handler
from handlers import start, status, today, unbind


def _configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
    )


async def main() -> None:
    _configure_logging()
    log = structlog.get_logger("telegram_bot")

    if not settings.telegram_bot_token:
        log.error("telegram_bot.missing_token")
        raise SystemExit(
            "TELEGRAM_BOT_TOKEN не задан. Подставь токен от BotFather в .env."
        )

    # Engine — здесь, а не на module-import, чтобы стартовые ошибки
    # подключения к БД писались в структурный лог (см. W10).
    init_engine()

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(start.router)
    dp.include_router(help_handler.router)
    dp.include_router(status.router)
    dp.include_router(today.router)
    dp.include_router(unbind.router)

    log.info("telegram_bot.starting", bot_username=settings.telegram_bot_username)
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
