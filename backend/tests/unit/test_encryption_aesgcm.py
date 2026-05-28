"""Unit-tests for AESGCMEncryptionService — production-grade crypto."""

from __future__ import annotations

import secrets

import pytest

from app.services.encryption_aesgcm import AESGCMEncryptionService
from app.services.encryption_service import (
    EncryptionError,
    SessionKeyNotFoundError,
)


class InMemoryRedis:
    """Минимальный стаб redis.asyncio.Redis."""

    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}

    async def get(self, key: str) -> bytes | None:
        return self._store.get(key)

    async def set(self, key: str, value: bytes, ex: int | None = None) -> None:  # noqa: ARG002
        self._store[key] = value

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)


@pytest.fixture
def service() -> AESGCMEncryptionService:
    return AESGCMEncryptionService(
        redis_keys_client=InMemoryRedis(),
        # Низкие параметры — для скорости тестов, не для production.
        memory_kib=8,
        time_cost=1,
        parallelism=1,
    )


# ---- KDF ------------------------------------------------------------- #


async def test_derive_user_key_returns_32_bytes(service) -> None:
    key = await service.derive_user_key("Str0ng!Password", b"\x00" * 32)
    assert isinstance(key, bytes)
    assert len(key) == 32


async def test_derive_user_key_is_deterministic(service) -> None:
    salt = secrets.token_bytes(32)
    k1 = await service.derive_user_key("samepass", salt)
    k2 = await service.derive_user_key("samepass", salt)
    assert k1 == k2


async def test_derive_user_key_differs_on_different_passwords(service) -> None:
    salt = b"\x01" * 32
    k1 = await service.derive_user_key("password-A", salt)
    k2 = await service.derive_user_key("password-B", salt)
    assert k1 != k2


async def test_derive_user_key_differs_on_different_salts(service) -> None:
    k1 = await service.derive_user_key("samepass", b"\x01" * 32)
    k2 = await service.derive_user_key("samepass", b"\x02" * 32)
    assert k1 != k2


# ---- encrypt_with_key / decrypt_with_key ----------------------------- #


async def test_encrypt_decrypt_with_key_roundtrip(service) -> None:
    key = secrets.token_bytes(32)
    plaintext = "Секретная информация о пациенте"
    ciphertext = await service.encrypt_with_key(plaintext, key)
    assert ciphertext != plaintext
    decrypted = await service.decrypt_with_key(ciphertext, key)
    assert decrypted == plaintext


async def test_encrypt_same_plaintext_produces_different_ciphertext(service) -> None:
    """Гарантия что nonce уникальный на каждое шифрование."""
    key = secrets.token_bytes(32)
    c1 = await service.encrypt_with_key("payload", key)
    c2 = await service.encrypt_with_key("payload", key)
    assert c1 != c2


async def test_decrypt_with_wrong_key_raises(service) -> None:
    key_a = secrets.token_bytes(32)
    key_b = secrets.token_bytes(32)
    ciphertext = await service.encrypt_with_key("data", key_a)
    with pytest.raises(EncryptionError):
        await service.decrypt_with_key(ciphertext, key_b)


async def test_decrypt_tampered_ciphertext_raises(service) -> None:
    """GCM tag должен ловить любую модификацию шифротекста."""
    key = secrets.token_bytes(32)
    ciphertext = await service.encrypt_with_key("data", key)
    # Меняем один символ в base64 (но оставляем длину валидной).
    tampered = ciphertext[:-2] + ("AA" if ciphertext[-2:] != "AA" else "BB")
    with pytest.raises(EncryptionError):
        await service.decrypt_with_key(tampered, key)


async def test_invalid_key_length_raises(service) -> None:
    with pytest.raises(EncryptionError):
        await service.encrypt_with_key("data", b"too-short")
    with pytest.raises(EncryptionError):
        await service.decrypt_with_key("anything", b"too-short")


# ---- DEK / Redis-backed session keys --------------------------------- #


async def test_encrypt_without_session_key_raises(service) -> None:
    with pytest.raises(SessionKeyNotFoundError):
        await service.encrypt("data", user_id=42)


async def test_encrypt_decrypt_via_session_dek_roundtrip(service) -> None:
    dek = secrets.token_bytes(32)
    await service.store_session_key(
        user_id=42, session_id="ignored", key=dek, ttl_seconds=60
    )
    ciphertext = await service.encrypt("hello", user_id=42)
    decrypted = await service.decrypt(ciphertext, user_id=42)
    assert decrypted == "hello"


async def test_session_key_is_per_user(service) -> None:
    dek_alice = secrets.token_bytes(32)
    dek_bob = secrets.token_bytes(32)
    await service.store_session_key(
        user_id=1, session_id="s", key=dek_alice, ttl_seconds=60
    )
    await service.store_session_key(
        user_id=2, session_id="s", key=dek_bob, ttl_seconds=60
    )
    ciphertext = await service.encrypt("alice's data", user_id=1)
    # Bob не сможет расшифровать данные Alice, даже если перехватит шифротекст.
    with pytest.raises(EncryptionError):
        await service.decrypt(ciphertext, user_id=2)


async def test_empty_string_passthrough(service) -> None:
    # Empty fields — оптимизация: не шифруем, не вызываем _load_dek.
    assert await service.encrypt("", user_id=1) == ""
    assert await service.decrypt("", user_id=1) == ""


async def test_revoke_session_key_is_noop_for_multi_device(service) -> None:
    """revoke не должен удалять DEK — другие сессии могут быть активны."""
    dek = secrets.token_bytes(32)
    await service.store_session_key(
        user_id=1, session_id="s", key=dek, ttl_seconds=60
    )
    await service.revoke_session_key(user_id=1, session_id="s")
    # Ключ всё ещё доступен.
    assert await service.get_session_key(user_id=1, session_id="other") == dek
