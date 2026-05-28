"""Unit-tests for sentry_init._before_send PII-фильтр."""

from __future__ import annotations

from app.sentry_init import _before_send


def test_password_in_request_data_is_redacted() -> None:
    event = {
        "request": {
            "data": {
                "email": "alice@example.com",
                "password": "Str0ng!Password",
                "password_confirm": "Str0ng!Password",
            }
        }
    }
    out = _before_send(event, {})
    assert out["request"]["data"]["password"] == "[REDACTED]"
    assert out["request"]["data"]["password_confirm"] == "[REDACTED]"
    # email замаскирован, не выпилен полностью.
    assert out["request"]["data"]["email"].startswith("a***@")


def test_recovery_phrase_is_redacted() -> None:
    event = {"extra": {"phrase": "abandon abandon ..."}}
    out = _before_send(event, {})
    assert out["extra"]["phrase"] == "[REDACTED]"


def test_authorization_header_is_redacted() -> None:
    event = {
        "request": {
            "headers": {
                "Authorization": "Bearer eyJxxx",
                "User-Agent": "Mozilla/5.0",
            }
        }
    }
    out = _before_send(event, {})
    assert out["request"]["headers"]["Authorization"] == "[REDACTED]"
    assert out["request"]["headers"]["User-Agent"] == "Mozilla/5.0"


def test_email_in_breadcrumb_message_is_masked() -> None:
    event = {
        "breadcrumbs": {
            "values": [
                {"message": "user alice@example.com logged in"},
            ]
        }
    }
    out = _before_send(event, {})
    msg = out["breadcrumbs"]["values"][0]["message"]
    assert "alice@example.com" not in msg
    assert "a***@e***" in msg


def test_user_payload_keeps_only_id() -> None:
    event = {"user": {"id": 42, "email": "alice@example.com", "ip_address": "1.2.3.4"}}
    out = _before_send(event, {})
    assert out["user"] == {"id": 42}


def test_nested_sensitive_keys_redacted() -> None:
    event = {
        "extra": {
            "form": {
                "user": {
                    "username": "alice",
                    "password": "secret",
                    "encrypted_dek": b"binary".hex(),
                }
            }
        }
    }
    out = _before_send(event, {})
    assert out["extra"]["form"]["user"]["username"] == "alice"
    assert out["extra"]["form"]["user"]["password"] == "[REDACTED]"
    assert out["extra"]["form"]["user"]["encrypted_dek"] == "[REDACTED]"
