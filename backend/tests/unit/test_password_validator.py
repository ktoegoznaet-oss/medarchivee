"""Unit tests for `validate_password_strength`."""

from __future__ import annotations

from app.services.password_validator import validate_password_strength


def test_strong_password_returns_no_errors() -> None:
    assert validate_password_strength("Strong!Passw0rd") == []


def test_too_short_password_is_rejected() -> None:
    errors = validate_password_strength("Aa1!aA1!")  # 8 chars
    assert "password_too_short" in errors


def test_missing_uppercase_is_rejected() -> None:
    errors = validate_password_strength("nouppercase!1234")
    assert "password_missing_uppercase" in errors


def test_missing_lowercase_is_rejected() -> None:
    errors = validate_password_strength("NOLOWERCASE!1234")
    assert "password_missing_lowercase" in errors


def test_missing_digit_is_rejected() -> None:
    errors = validate_password_strength("NoDigitsHere!Abc")
    assert "password_missing_digit" in errors


def test_missing_special_is_rejected() -> None:
    errors = validate_password_strength("NoSpecialChar1234")
    assert "password_missing_special" in errors


def test_password_matches_email_is_rejected() -> None:
    errors = validate_password_strength(
        "John@Example1234!",
        email="john@example.com",
        username="johnny",
    )
    assert "password_matches_email" in errors


def test_password_matches_username_is_rejected() -> None:
    errors = validate_password_strength(
        "Johnny!2026Strong",
        email="me@example.com",
        username="johnny",
    )
    assert "password_matches_username" in errors
