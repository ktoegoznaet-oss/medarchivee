"""/status handler — статус привязки + текущие настройки уведомлений."""

from __future__ import annotations

from aiogram import Router, types
from aiogram.filters import Command

from db.binding import find_binding
from db.session import session_factory
from handlers.texts import NOT_BOUND, bound_status_text

router = Router()


@router.message(Command("status"))
async def cmd_status(message: types.Message) -> None:
    sender = message.from_user
    if sender is None:
        return

    binding = await find_binding(session_factory(), sender.id)
    if binding is None:
        await message.answer(NOT_BOUND, parse_mode="HTML")
        return
    await message.answer(
        bound_status_text(
            username=binding.telegram_username,
            bound_at=binding.bound_at,
            notifications_enabled=binding.notifications_enabled,
            notify_medications=binding.notify_medications,
            notify_visits=binding.notify_visits,
            notify_daily_summary=binding.notify_daily_summary,
        ),
        parse_mode="HTML",
    )
