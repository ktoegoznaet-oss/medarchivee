"""/unbind handler — с подтверждением через inline-кнопку."""

from __future__ import annotations

import structlog
from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from db.binding import find_binding, unbind
from db.session import session_factory
from handlers.texts import (
    NOT_BOUND,
    UNBIND_CONFIRM,
    UNBIND_DONE,
    UNBIND_KEEP,
)

router = Router()
log = structlog.get_logger(__name__)

_CONFIRM_CALLBACK = "unbind:confirm"
_KEEP_CALLBACK = "unbind:keep"


def _confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🔓 Да, отвязать",
                    callback_data=_CONFIRM_CALLBACK,
                ),
                InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data=_KEEP_CALLBACK,
                ),
            ]
        ]
    )


@router.message(Command("unbind"))
async def cmd_unbind(message: types.Message) -> None:
    sender = message.from_user
    if sender is None:
        return

    binding = await find_binding(session_factory(), sender.id)
    if binding is None:
        await message.answer(NOT_BOUND, parse_mode="HTML")
        return
    await message.answer(
        UNBIND_CONFIRM,
        reply_markup=_confirm_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == _CONFIRM_CALLBACK)
async def on_confirm(callback: types.CallbackQuery) -> None:
    sender = callback.from_user
    if sender is None or callback.message is None:
        await callback.answer()
        return
    ok = await unbind(session_factory(), sender.id)
    await callback.message.edit_text(
        UNBIND_DONE if ok else NOT_BOUND, parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == _KEEP_CALLBACK)
async def on_keep(callback: types.CallbackQuery) -> None:
    if callback.message is not None:
        await callback.message.edit_text(UNBIND_KEEP, parse_mode="HTML")
    await callback.answer()
