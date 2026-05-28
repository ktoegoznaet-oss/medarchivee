"""High-level EmailService — ставит письма в ARQ-очередь.

Бизнес-код вызывает только `EmailService.enqueue_*` методы; они формируют
EmailMessage через шаблоны и ставят задачу `send_email_task` в очередь.
Реальная SMTP-отправка происходит в воркере (`backend/app/workers/mailer.py`).

В тестах вместо ARQ-pool передаём `InProcessQueue` — он отправляет письма
сразу, синхронно. Это удобнее, чем поднимать целый Redis в pytest.
"""

from __future__ import annotations

from typing import Protocol

import structlog

from app.services.email.sender import EmailMessage, EmailSender
from app.services.email.templates import EmailTemplates

log = structlog.get_logger(__name__)


class EmailQueue(Protocol):
    """Минимальный контракт очереди для тестов и реальной реализации."""

    async def enqueue(self, message: EmailMessage) -> None: ...


class InProcessQueue:
    """Test-double: отправляет письма сразу, синхронно, без Redis.

    Не для прода. В прод используется `ArqEmailQueue` (см. dependencies.py).
    """

    def __init__(self, sender: EmailSender) -> None:
        self._sender = sender

    async def enqueue(self, message: EmailMessage) -> None:
        await self._sender.send(message)


class ArqEmailQueue:
    """Кладёт задачу `send_email_task` в ARQ-pool.

    Тело письма передаётся как dict (ARQ сериализует через msgpack/pickle),
    воркер сам соберёт EmailMessage и отправит через SmtpEmailSender.
    """

    def __init__(self, pool, task_name: str = "send_email_task") -> None:  # type: ignore[no-untyped-def]
        self._pool = pool
        self._task_name = task_name

    async def enqueue(self, message: EmailMessage) -> None:
        await self._pool.enqueue_job(
            self._task_name,
            {
                "subject": message.subject,
                "to": message.to,
                "text": message.text,
                "html": message.html,
                "headers": message.headers,
            },
        )
        log.info(
            "email.enqueued",
            to=message.to,
            subject=message.subject,
        )


class EmailService:
    """Фасад для бизнес-кода: «отправь письмо такого-то типа»."""

    def __init__(
        self,
        *,
        queue: EmailQueue,
        templates: EmailTemplates,
        frontend_base_url: str,
    ) -> None:
        self._queue = queue
        self._templates = templates
        self._frontend_base_url = frontend_base_url

    async def send_verification_code(
        self,
        *,
        to: str,
        code: str,
        username: str,
        ttl_hours: int,
    ) -> None:
        message = self._templates.verify_email(
            to=to,
            code=code,
            username=username,
            frontend_base_url=self._frontend_base_url,
            ttl_hours=ttl_hours,
        )
        await self._queue.enqueue(message)

    async def send_wipe_code(self, *, to: str, code: str) -> None:
        message = self._templates.wipe_account(to=to, code=code)
        await self._queue.enqueue(message)
