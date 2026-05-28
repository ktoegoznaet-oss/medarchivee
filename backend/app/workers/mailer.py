"""ARQ worker for delivering queued emails.

Запускается отдельным контейнером `mailer_worker` (см. docker-compose).
Один процесс, по одному воркеру — нам не нужна параллельная отправка для
~10 беты-пользователей. Можем поднять concurrency позже, когда поток писем
вырастет.

Конфигурация:
  * Берёт SMTP из `settings.smtp_*`.
  * При пустом `SMTP_USER` использует `LogEmailSender` (dev fallback).
    Прод-валидатор в `config.py` запрещает старт с пустым SMTP_USER в
    APP_ENV=production, так что LogEmailSender в проде не активируется.
  * Логирует каждое успешное отправление и каждый retry (ARQ повторяет
    задачу при exception до max_tries раз).
"""

from __future__ import annotations

from typing import Any

import structlog
from arq.connections import RedisSettings

from app.config import settings
from app.logging_config import configure_logging
from app.services.email.sender import (
    EmailMessage,
    EmailSender,
    LogEmailSender,
    SmtpEmailSender,
)

log = structlog.get_logger(__name__)


def _build_sender() -> EmailSender:
    if not settings.smtp_user:
        log.warning("email.worker.using_log_fallback")
        return LogEmailSender()
    return SmtpEmailSender(
        host=settings.smtp_host,
        port=settings.smtp_port,
        user=settings.smtp_user,
        password=settings.smtp_password,
        from_email=settings.smtp_from_email or settings.smtp_user,
        from_name=settings.smtp_from_name,
        use_ssl=settings.smtp_use_ssl,
        timeout_seconds=settings.smtp_timeout_seconds,
    )


async def startup(ctx: dict[str, Any]) -> None:
    configure_logging()
    ctx["sender"] = _build_sender()
    log.info(
        "email.worker.started",
        smtp_host=settings.smtp_host,
        smtp_port=settings.smtp_port,
        fallback=not settings.smtp_user,
    )


async def shutdown(ctx: dict[str, Any]) -> None:
    log.info("email.worker.stopped")


async def send_email_task(ctx: dict[str, Any], payload: dict[str, Any]) -> None:
    sender: EmailSender = ctx["sender"]
    message = EmailMessage(
        subject=payload["subject"],
        to=payload["to"],
        text=payload["text"],
        html=payload.get("html"),
        headers=payload.get("headers") or {},
    )
    try:
        await sender.send(message)
    except Exception as exc:  # noqa: BLE001 — пробрасываем, чтобы ARQ ретраил
        log.error(
            "email.worker.send_failed",
            to=message.to,
            subject=message.subject,
            error=str(exc),
        )
        raise


class WorkerSettings:
    """ARQ entrypoint — `arq app.workers.mailer.WorkerSettings`."""

    functions = [send_email_task]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings(
        host=settings.redis_host,
        port=settings.redis_port,
        database=settings.arq_redis_db,
    )
    max_tries = 3
    job_timeout = 60
