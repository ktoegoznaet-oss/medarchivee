"""Unit tests for EmailTemplates — Jinja2 rendering."""

from __future__ import annotations

from app.services.email.templates import build_default_templates


def test_verify_email_template_contains_code_and_username() -> None:
    templates = build_default_templates()
    message = templates.verify_email(
        to="alice@example.com",
        code="123456",
        username="alice",
        frontend_base_url="https://medarchive.example.com",
        ttl_hours=24,
    )
    assert message.to == "alice@example.com"
    assert "123456" in message.text
    assert "123456" in (message.html or "")
    assert "alice" in message.text
    assert "alice" in (message.html or "")
    assert "24" in message.text
    assert message.subject == "Подтверждение регистрации в МедАрхив"
    # Subject marker должен быть удалён из HTML тела.
    assert "subject:" not in (message.html or "")


def test_verify_email_link_uses_frontend_base_url() -> None:
    templates = build_default_templates()
    message = templates.verify_email(
        to="alice@example.com",
        code="123456",
        username="alice",
        frontend_base_url="https://prod.example.com",
        ttl_hours=24,
    )
    assert "https://prod.example.com/verify-email" in (message.html or "")
    assert "https://prod.example.com/verify-email" in message.text


def test_html_escapes_unsafe_username() -> None:
    templates = build_default_templates()
    message = templates.verify_email(
        to="alice@example.com",
        code="123456",
        username="<script>alert(1)</script>",
        frontend_base_url="http://test",
        ttl_hours=24,
    )
    # Jinja2 autoescape должен превратить < в &lt; в HTML.
    assert "<script>" not in (message.html or "")
    assert "&lt;script&gt;" in (message.html or "")
    # А в текстовом — оставить как есть (текст не autoescape'ится).
    assert "<script>" in message.text
