"""Tests for IdentityEncryptionService — the stage 1–6 passthrough stub."""

from __future__ import annotations

import structlog
from structlog.testing import capture_logs

from app.services.encryption_identity import IdentityEncryptionService


async def test_encrypt_decrypt_round_trip() -> None:
    svc = IdentityEncryptionService()

    ciphertext = await svc.encrypt("медицинский анамнез", user_id=42)
    plaintext = await svc.decrypt(ciphertext, user_id=42)

    assert plaintext == "медицинский анамнез"


async def test_encrypt_empty_string_is_handled() -> None:
    svc = IdentityEncryptionService()

    assert await svc.encrypt("", user_id=1) == ""
    assert await svc.decrypt("", user_id=1) == ""


async def test_derive_user_key_returns_exactly_32_bytes() -> None:
    svc = IdentityEncryptionService()

    key = await svc.derive_user_key(password="any", salt=b"\x00" * 32)

    assert isinstance(key, bytes)
    assert len(key) == 32


async def test_session_key_lifecycle_is_no_op() -> None:
    svc = IdentityEncryptionService()

    # Stage 1: no Redis. These calls must not raise.
    await svc.store_session_key(user_id=1, session_id="abc", key=b"x" * 32, ttl_seconds=900)
    key = await svc.get_session_key(user_id=1, session_id="abc")
    await svc.revoke_session_key(user_id=1, session_id="abc")

    assert key is not None and len(key) == 32


async def test_encrypt_with_key_round_trip() -> None:
    svc = IdentityEncryptionService()
    key = b"\xaa" * 32

    ciphertext = await svc.encrypt_with_key("резервная копия", key=key)
    plaintext = await svc.decrypt_with_key(ciphertext, key=key)

    assert plaintext == "резервная копия"


async def test_encrypt_emits_debug_log_with_user_id_but_not_plaintext() -> None:
    svc = IdentityEncryptionService()
    # capture_logs хватает события structlog без stdlib-логгера.
    with capture_logs() as logs:
        structlog.contextvars.clear_contextvars()
        await svc.encrypt("секретные данные", user_id=7)

    encrypt_events = [e for e in logs if e["event"] == "encryption.identity.encrypt"]
    assert len(encrypt_events) == 1
    event = encrypt_events[0]
    assert event["user_id"] == 7
    # Главная инвариант: plaintext не попадает в логи.
    assert "секретные данные" not in str(event)
