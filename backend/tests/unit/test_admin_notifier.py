"""Unit-tests for AdminNotifier formatting + NullAdminNotifier."""

from __future__ import annotations

from app.services.admin_telegram import NullAdminNotifier
from app.services.admin_telegram.notifier import (
    AdminNotifier,
    format_critical_error,
    format_new_registration,
    format_new_ticket,
)


async def test_null_notifier_records_calls() -> None:
    notifier = NullAdminNotifier()
    await notifier.notify("hello")
    await notifier.notify("world")
    assert notifier.sent == ["hello", "world"]


async def test_notifier_disabled_without_config() -> None:
    """Пустой token / chat_id → notify это no-op, не падает."""
    notifier = AdminNotifier(bot_token="", chat_id="")
    await notifier.notify("would crash if it tried httpx")


def test_format_new_registration_escapes_html() -> None:
    msg = format_new_registration(
        email="x@<script>.com", username="<b>bad</b>", role="user"
    )
    assert "<script>" not in msg
    assert "&lt;script&gt;" in msg
    assert "&lt;b&gt;bad&lt;/b&gt;" in msg
    assert "user" in msg


def test_format_new_ticket_truncates_long_title() -> None:
    long_title = "X" * 500
    msg = format_new_ticket(
        ticket_id=42,
        user_email="alice@example.com",
        ticket_type="bug",
        title=long_title,
    )
    assert "#42" in msg
    assert "alice@example.com" in msg
    # Заголовок обрезан до 100 символов.
    assert "X" * 100 in msg
    assert "X" * 101 not in msg


def test_format_critical_error_includes_source_and_message() -> None:
    msg = format_critical_error(source="auth_service", message="boom!")
    assert "auth_service" in msg
    assert "boom!" in msg
    assert "🚨" in msg
