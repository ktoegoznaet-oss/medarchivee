"""Sentry / GlitchTip initialization with PII-filtering.

КРИТИЧНО: МедАрхив — это медданные. В Sentry/GlitchTip НЕ ДОЛЖНЫ
попадать:
  * пароли (form fields password / password_confirm / new_password)
  * мнемонические фразы (recovery phrase)
  * содержимое медицинских записей (расшифрованные plaintext)
  * раскодированный DEK / KEK
  * полный email (маскируется до 'a***@b***.tld')
  * JWT access/refresh токены

before_send hook здесь — последний рубеж: даже если разработчик
случайно положит чувствительное поле в exception breadcrumb, hook
его удалит до отправки.
"""

from __future__ import annotations

import re
from typing import Any

import structlog

log = structlog.get_logger(__name__)

_SENSITIVE_KEYS = {
    "password",
    "password_confirm",
    "new_password",
    "new_password_confirm",
    "phrase",
    "recovery_phrase",
    "confirmation_words",
    "code",  # email verification codes / wipe codes / invite codes
    "invite_code",
    "encrypted_dek",
    "recovery_master_key",
    "access_token",
    "refresh_token",
    "jwt_secret",
    "secret_key",
    "smtp_password",
    "telegram_bot_token",
    "telegram_admin_bot_token",
}
_REDACTED = "[REDACTED]"
_EMAIL_RE = re.compile(r"\b([A-Za-z0-9_.+-]+)@([A-Za-z0-9.-]+)\.([A-Za-z]{2,})\b")


def _mask_email(match: re.Match[str]) -> str:
    local = match.group(1)
    domain = match.group(2)
    tld = match.group(3)
    return f"{local[0]}***@{domain[0]}***.{tld}"


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: (_REDACTED if k.lower() in _SENSITIVE_KEYS else _sanitize(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_sanitize(v) for v in value]
    if isinstance(value, str):
        return _EMAIL_RE.sub(_mask_email, value)
    return value


def _before_send(event: dict[str, Any], _hint: dict[str, Any]) -> dict[str, Any] | None:
    """Удаляет чувствительные поля из event до отправки в Sentry."""
    if "request" in event and isinstance(event["request"], dict):
        req = event["request"]
        if "data" in req:
            req["data"] = _sanitize(req["data"])
        if "headers" in req and isinstance(req["headers"], dict):
            for h in list(req["headers"].keys()):
                if h.lower() in {"authorization", "cookie"}:
                    req["headers"][h] = _REDACTED

    if "extra" in event and isinstance(event["extra"], dict):
        event["extra"] = _sanitize(event["extra"])

    if "breadcrumbs" in event and isinstance(event["breadcrumbs"], dict):
        values = event["breadcrumbs"].get("values", [])
        for crumb in values:
            if isinstance(crumb, dict):
                if "data" in crumb:
                    crumb["data"] = _sanitize(crumb["data"])
                if "message" in crumb and isinstance(crumb["message"], str):
                    crumb["message"] = _EMAIL_RE.sub(_mask_email, crumb["message"])

    # user — оставляем только id, убираем email/ip
    if "user" in event and isinstance(event["user"], dict):
        user = event["user"]
        event["user"] = {"id": user.get("id")} if "id" in user else {}

    return event


def init_sentry(dsn: str, environment: str, traces_sample_rate: float = 0.0) -> bool:
    """Идемпотентная инициализация. Возвращает True если SDK включён."""
    if not dsn:
        log.info("sentry.disabled_no_dsn")
        return False
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        traces_sample_rate=traces_sample_rate,
        send_default_pii=False,  # никогда не отправлять PII по умолчанию
        max_request_body_size="never",  # вообще не пытаемся прислать тело запроса
        before_send=_before_send,
        integrations=[
            FastApiIntegration(transaction_style="endpoint"),
            SqlalchemyIntegration(),
        ],
    )
    log.info("sentry.initialized", environment=environment)
    return True
