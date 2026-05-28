"""AdminNotifier — fire-and-forget Telegram push.

Реальная реализация шлёт через api.telegram.org/sendMessage с timeout=5s.
Если токен/chat_id не сконфигурированы или сеть упала — тихо логируем
warning, не блокируем основной flow.

В тестах используется NullAdminNotifier, который собирает вызовы в
память.
"""

from __future__ import annotations

import asyncio
import html
from typing import Protocol

import httpx
import structlog

log = structlog.get_logger(__name__)

_TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"


class AdminNotifierProtocol(Protocol):
    async def notify(self, text: str) -> None: ...


class AdminNotifier:
    """Production-ready notifier. Не падает при ошибках сети — лог + дальше."""

    def __init__(
        self,
        *,
        bot_token: str,
        chat_id: str,
        timeout_seconds: int = 5,
    ):
        self._token = bot_token
        self._chat_id = chat_id
        self._timeout = timeout_seconds
        self._enabled = bool(bot_token) and bool(chat_id)

    async def notify(self, text: str) -> None:
        if not self._enabled:
            log.debug("admin_telegram.notify_skipped_no_config", text_len=len(text))
            return
        # Fire-and-forget: не ждём ответа Telegram, чтобы не задержать
        # пользовательский запрос. Если задача упадёт — лог-warning.
        asyncio.create_task(self._send(text))

    async def _send(self, text: str) -> None:
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    _TELEGRAM_API_URL.format(token=self._token),
                    json={
                        "chat_id": self._chat_id,
                        "text": text,
                        "parse_mode": "HTML",
                        "disable_web_page_preview": True,
                    },
                )
                if resp.status_code >= 400:
                    log.warning(
                        "admin_telegram.notify_failed",
                        status=resp.status_code,
                        body=resp.text[:200],
                    )
        except Exception as exc:  # noqa: BLE001
            log.warning("admin_telegram.notify_exception", error=str(exc))


class NullAdminNotifier:
    """No-op для тестов / dev без сконфигурированного бота."""

    def __init__(self) -> None:
        self.sent: list[str] = []

    async def notify(self, text: str) -> None:
        self.sent.append(text)


def format_new_registration(*, email: str, username: str, role: str) -> str:
    safe_email = html.escape(email)
    safe_username = html.escape(username)
    return (
        "🆕 <b>Новая регистрация</b>\n"
        f"Email: <code>{safe_email}</code>\n"
        f"Username: <code>{safe_username}</code>\n"
        f"Роль: {html.escape(role)}"
    )


def format_new_ticket(
    *,
    ticket_id: int,
    user_email: str,
    ticket_type: str,
    title: str,
) -> str:
    safe_title = html.escape(title[:100])
    safe_email = html.escape(user_email)
    return (
        "🎫 <b>Новый тикет</b>\n"
        f"#{ticket_id} · {html.escape(ticket_type)}\n"
        f"От: <code>{safe_email}</code>\n"
        f"<b>{safe_title}</b>"
    )


def format_critical_error(*, source: str, message: str) -> str:
    return (
        f"🚨 <b>Критическая ошибка</b> ({html.escape(source)})\n"
        f"<pre>{html.escape(message[:500])}</pre>"
    )
