"""AES-256-GCM encryption + Argon2id KDF — production-grade реализация.

Архитектура (двухслойная):

  Пароль пользователя
        │
        ▼  Argon2id (encryption_salt, m=46MiB t=1 p=1 по умолчанию)
        │
       KEK (32 байта) — Key Encryption Key
        │
        ▼  AES-256-GCM
        │
   encrypted_dek (в users.encrypted_dek)
        │
        ▼ дешифровка при логине
        │
       DEK (32 байта) — Data Encryption Key, случайные байты
        │            (генерируются один раз при регистрации,
        │             никогда не меняется)
        │
        ▼  AES-256-GCM (per-field unique 12-byte nonce)
        │
   Зашифрованные медицинские поля в БД

DEK живёт в redis_keys на время refresh-token TTL под ключом
`user:{user_id}:dek`. При компрометации дампа БД злоумышленник видит
только encrypted_dek (бесполезен без KEK из пароля) и зашифрованные
данные (бесполезны без DEK). При компрометации Redis_keys (in-memory)
ключи видны только во время аптайма — на диске их нет.

Формат шифротекста на диске:
  base64( nonce(12 байт) || ciphertext_with_gcm_tag )
Размер шифротекста = размер plaintext + 12 (nonce) + 16 (GCM tag).
"""

from __future__ import annotations

import base64
import secrets

import structlog
from argon2.low_level import Type, hash_secret_raw
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag

from app.services.encryption_service import (
    EncryptionError,
    EncryptionService,
    SessionKeyNotFoundError,
)

log = structlog.get_logger(__name__)

_NONCE_BYTES = 12
_KEY_BYTES = 32  # AES-256


class DekNotInitializedError(EncryptionError):
    """encrypted_dek отсутствует у пользователя — нужна перерегистрация
    или ручное восстановление DEK (Шаг F через мнемонику)."""


class _RedisProtocol:
    """Subset of redis.asyncio.Redis methods we actually use.

    Объявлен здесь, чтобы тесты могли подменить inmemory-реализацией без
    подъёма настоящего Redis. См. `InMemoryKeyStore` в tests.
    """

    async def get(self, key: str) -> bytes | None: ...
    async def set(self, key: str, value: bytes, ex: int | None = None) -> None: ...
    async def delete(self, key: str) -> None: ...


def _session_key_name(user_id: int) -> str:
    """One key per user (НЕ per session) — DEK не меняется между сессиями.

    Multi-device login: одни и те же байты DEK переписываются в Redis с
    обновлённым TTL. Logout не удаляет ключ — он истекает по TTL.
    Это упрощает многосессионное использование (логин с двух устройств
    не конфликтует) и не снижает безопасность: ключ всё равно живёт
    только пока активен хоть один refresh-токен.
    """
    return f"user:{user_id}:dek"


class AESGCMEncryptionService(EncryptionService):
    """Реализация EncryptionService через AES-256-GCM + Argon2id KDF."""

    def __init__(
        self,
        *,
        redis_keys_client: _RedisProtocol,
        memory_kib: int,
        time_cost: int,
        parallelism: int,
    ):
        self._redis = redis_keys_client
        self._memory_kib = memory_kib
        self._time_cost = time_cost
        self._parallelism = parallelism

    # ---- KDF ------------------------------------------------------------- #

    async def derive_user_key(self, password: str, salt: bytes) -> bytes:
        """Argon2id(password, salt) → 32-byte KEK.

        Параметры берутся из конфига при создании сервиса. Detached
        от Argon2id PasswordHasher — нам нужен raw key, не hash-строка.
        """
        return hash_secret_raw(
            secret=password.encode("utf-8"),
            salt=salt,
            time_cost=self._time_cost,
            memory_cost=self._memory_kib,
            parallelism=self._parallelism,
            hash_len=_KEY_BYTES,
            type=Type.ID,
        )

    # ---- Низкоуровневое шифрование с произвольным ключом ----------------- #

    async def encrypt_with_key(self, plaintext: str, key: bytes) -> str:
        if len(key) != _KEY_BYTES:
            raise EncryptionError(
                f"AES-256 key must be {_KEY_BYTES} bytes, got {len(key)}"
            )
        nonce = secrets.token_bytes(_NONCE_BYTES)
        ciphertext = AESGCM(key).encrypt(nonce, plaintext.encode("utf-8"), None)
        return base64.b64encode(nonce + ciphertext).decode("ascii")

    async def decrypt_with_key(self, ciphertext: str, key: bytes) -> str:
        if len(key) != _KEY_BYTES:
            raise EncryptionError(
                f"AES-256 key must be {_KEY_BYTES} bytes, got {len(key)}"
            )
        try:
            data = base64.b64decode(ciphertext)
        except Exception as exc:  # noqa: BLE001
            raise EncryptionError("invalid base64 ciphertext") from exc
        if len(data) < _NONCE_BYTES + 16:  # nonce + min GCM tag
            raise EncryptionError("ciphertext too short")
        nonce, ct = data[:_NONCE_BYTES], data[_NONCE_BYTES:]
        try:
            plaintext = AESGCM(key).decrypt(nonce, ct, None)
        except InvalidTag as exc:
            raise EncryptionError("ciphertext tampered or wrong key") from exc
        return plaintext.decode("utf-8")

    # ---- DEK / Redis ----------------------------------------------------- #

    async def store_session_key(
        self,
        user_id: int,
        session_id: str,  # noqa: ARG002 — не используется (см. _session_key_name)
        key: bytes,
        ttl_seconds: int,
    ) -> None:
        if len(key) != _KEY_BYTES:
            raise EncryptionError(
                f"DEK must be {_KEY_BYTES} bytes, got {len(key)}"
            )
        await self._redis.set(
            _session_key_name(user_id), key, ex=ttl_seconds
        )
        log.debug(
            "encryption.session_key_stored",
            user_id=user_id,
            ttl_seconds=ttl_seconds,
        )

    async def get_session_key(
        self,
        user_id: int,
        session_id: str,  # noqa: ARG002
    ) -> bytes | None:
        return await self._redis.get(_session_key_name(user_id))

    async def revoke_session_key(
        self,
        user_id: int,
        session_id: str,  # noqa: ARG002
    ) -> None:
        # При logout НЕ удаляем ключ: у пользователя могут быть другие
        # активные refresh-токены на других устройствах, и мы не хотим
        # их сломать. Ключ истечёт сам по TTL после последнего refresh.
        # Это решение задокументировано в _session_key_name docstring.
        log.debug("encryption.session_key_revoke_noop", user_id=user_id)

    # ---- Высокоуровневое шифрование данных по user_id -------------------- #

    async def _load_dek(self, user_id: int) -> bytes:
        dek = await self._redis.get(_session_key_name(user_id))
        if dek is None:
            raise SessionKeyNotFoundError(
                f"DEK for user {user_id} missing — requires re-login"
            )
        if len(dek) != _KEY_BYTES:
            raise EncryptionError(
                f"DEK in Redis has wrong length: {len(dek)}"
            )
        return dek

    async def encrypt(self, plaintext: str, user_id: int) -> str:
        if plaintext == "":
            # AES-GCM шифрует и пустую строку, но это лишняя нагрузка для
            # типичных опциональных полей. Возвращаем маркер пустоты.
            return ""
        dek = await self._load_dek(user_id)
        return await self.encrypt_with_key(plaintext, dek)

    async def decrypt(self, ciphertext: str, user_id: int) -> str:
        if ciphertext == "":
            return ""
        dek = await self._load_dek(user_id)
        return await self.decrypt_with_key(ciphertext, dek)


def generate_dek() -> bytes:
    """Случайный 32-байтный DEK — генерируется один раз при регистрации."""
    return secrets.token_bytes(_KEY_BYTES)
