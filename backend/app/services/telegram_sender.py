"""Thin async wrapper around the Telegram Bot API.

Used by:
  * backend — для тестового сообщения (`/telegram/binding/test`) и в будущем
    для системных уведомлений (этапы 9–10).
  * `telegram_bot` сервис — у него есть своя aiogram-обёртка, но прямые
    вызовы Bot API из backend идут через эту обёртку, чтобы не тащить
    aiogram в backend.

Безопасность (§9.1 v1.1): любое сообщение, отправляемое отсюда, идёт через
серверы Telegram. Вызывающая сторона обязана НЕ передавать сюда диагнозы,
конкретные значения анализов и прочее чувствительное содержимое — только
метаданные (тип события, время).
"""

from __future__ import annotations

import httpx
import structlog

log = structlog.get_logger(__name__)


class TelegramSender:
    def __init__(self, bot_token: str, timeout_seconds: float = 10.0) -> None:
        self._token = bot_token
        self._base_url = f"https://api.telegram.org/bot{bot_token}"
        self._timeout = timeout_seconds

    async def send_message(
        self,
        chat_id: int,
        text: str,
        *,
        parse_mode: str = "HTML",
    ) -> bool:
        """Send `text` to `chat_id`. Returns True on success, False on any error.

        Не пробрасывает исключение наружу: вызывающие сценарии (тестовое
        сообщение, фоновые рассылки) хотят знать «доставилось/нет», а не
        падать на сетевых проблемах.
        """
        if not self._token:
            log.warning("telegram_sender.no_token", chat_id=chat_id)
            return False
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    f"{self._base_url}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": text,
                        "parse_mode": parse_mode,
                    },
                )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            log.error(
                "telegram_sender.send_failed",
                chat_id=chat_id,
                error=str(exc),
            )
            return False
        log.info("telegram_sender.sent", chat_id=chat_id)
        return True
