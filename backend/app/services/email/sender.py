"""Low-level email senders.

`EmailSender` — формальный интерфейс. Две реализации:
  * `SmtpEmailSender` — отправляет через aiosmtplib (Yandex SMTP по умолчанию).
  * `LogEmailSender` — пишет письмо в structlog. Используется в тестах и в
    dev-окружении при пустом `SMTP_USER`. На pre-prod/prod валидатор
    `config.smtp_user` запрещает запуск с пустым SMTP_USER.

Никогда не логируем содержимое писем целиком — только subject, to, длину
text/html. Содержимое может включать одноразовые коды верификации, которые
не должны попадать в долгоживущие логи.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from email.message import EmailMessage as MimeEmailMessage
from typing import Protocol

import aiosmtplib
import structlog

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class EmailMessage:
    """Готовое к отправке сообщение.

    `subject`, `to`, `text`, `html` — все обязательны кроме html (опционально,
    но крайне рекомендуется для UX). `headers` — дополнительные заголовки
    (например, Reply-To). От поля `from_*` решает sender, чтобы письма всегда
    уходили от одного отправителя.
    """

    subject: str
    to: str
    text: str
    html: str | None = None
    headers: dict[str, str] = field(default_factory=dict)


class EmailSender(Protocol):
    async def send(self, message: EmailMessage) -> None: ...


class SmtpEmailSender:
    """aiosmtplib-based sender для Yandex SMTP и аналогов.

    SSL по умолчанию (порт 465 у Yandex). Не реализуем retry — оставляем
    его на уровне очереди (ARQ повторит задачу при исключении).
    """

    def __init__(
        self,
        *,
        host: str,
        port: int,
        user: str,
        password: str,
        from_email: str,
        from_name: str,
        use_ssl: bool = True,
        timeout_seconds: int = 30,
    ) -> None:
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._from_email = from_email or user
        self._from_name = from_name
        self._use_ssl = use_ssl
        self._timeout = timeout_seconds

    async def send(self, message: EmailMessage) -> None:
        mime = MimeEmailMessage()
        mime["Subject"] = message.subject
        mime["From"] = f"{self._from_name} <{self._from_email}>"
        mime["To"] = message.to
        for header, value in message.headers.items():
            mime[header] = value
        mime.set_content(message.text)
        if message.html:
            mime.add_alternative(message.html, subtype="html")

        await aiosmtplib.send(
            mime,
            hostname=self._host,
            port=self._port,
            username=self._user,
            password=self._password,
            use_tls=self._use_ssl,
            timeout=self._timeout,
        )
        log.info(
            "email.sent",
            to=message.to,
            subject=message.subject,
            text_len=len(message.text),
            html_len=len(message.html or ""),
        )


class LogEmailSender:
    """Fallback-sender: пишет письмо в лог вместо отправки.

    Используется в тестах и в dev (когда SMTP_USER пустой). На проде такой
    sender не должен инициализироваться — отвечает за это валидатор в
    `config.smtp_user`.
    """

    async def send(self, message: EmailMessage) -> None:
        log.info(
            "email.dev_fallback",
            to=message.to,
            subject=message.subject,
            text=message.text,
            html_len=len(message.html or ""),
        )
