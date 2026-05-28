"""/today handler — заглушка для этапа 6 (см. §9 ТЗ, реальный контент — этап 10)."""

from __future__ import annotations

from aiogram import Router, types
from aiogram.filters import Command

from db.binding import find_binding
from db.session import session_factory
from handlers.texts import NOT_BOUND, TODAY_PLACEHOLDER

router = Router()


@router.message(Command("today"))
async def cmd_today(message: types.Message) -> None:
    sender = message.from_user
    if sender is None:
        return

    binding = await find_binding(session_factory(), sender.id)
    if binding is None:
        await message.answer(NOT_BOUND, parse_mode="HTML")
        return
    await message.answer(TODAY_PLACEHOLDER, parse_mode="HTML")
