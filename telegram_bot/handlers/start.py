"""/start handler — поддерживает deep-link с кодом привязки."""

from __future__ import annotations

import structlog
from aiogram import Router, types
from aiogram.filters import Command, CommandObject

from db.binding import find_binding, try_bind
from db.session import session_factory
from handlers.rate_limit import binding_attempt_limiter
from handlers.texts import (
    GREETING_WITH_INSTRUCTIONS,
    HELLO_AGAIN,
    INVALID_CODE_LABELS,
    bind_failure_text,
    bind_success_text,
)

router = Router()
log = structlog.get_logger(__name__)


@router.message(Command("start"))
async def cmd_start(message: types.Message, command: CommandObject) -> None:
    sender = message.from_user
    if sender is None:
        return

    if command.args:
        if not await binding_attempt_limiter.allow(sender.id):
            await message.answer(
                "Слишком много попыток. Подождите минуту и попробуйте снова."
            )
            return

        result = await try_bind(
            session_factory(),
            code=command.args.strip(),
            telegram_user_id=sender.id,
            telegram_username=sender.username,
        )
        if result.ok:
            log.info(
                "telegram_bot.start_bind_ok",
                telegram_user_id=sender.id,
                user_id=result.user_id,
            )
            await message.answer(
                bind_success_text(sender.first_name or "друг"),
                parse_mode="HTML",
            )
        else:
            label = INVALID_CODE_LABELS.get(result.error or "", "неизвестная ошибка")
            log.info(
                "telegram_bot.start_bind_failed",
                telegram_user_id=sender.id,
                error=result.error,
            )
            await message.answer(bind_failure_text(label))
        return

    binding = await find_binding(session_factory(), sender.id)
    if binding is not None:
        await message.answer(
            HELLO_AGAIN.format(name=sender.first_name or "друг"),
            parse_mode="HTML",
        )
    else:
        await message.answer(
            GREETING_WITH_INSTRUCTIONS,
            parse_mode="HTML",
        )
