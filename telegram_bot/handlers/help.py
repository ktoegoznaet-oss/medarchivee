"""/help handler — справка с дисклеймером (§9.1)."""

from __future__ import annotations

from aiogram import Router, types
from aiogram.filters import Command

from handlers.texts import HELP_TEXT

router = Router()


@router.message(Command("help"))
async def cmd_help(message: types.Message) -> None:
    await message.answer(HELP_TEXT, parse_mode="HTML")
