"""Identity encryption stub.

Returns plaintext verbatim. Used on stages 1–6 so that downstream services can
already call `encrypt(...)` / `decrypt(...)` with the correct signatures — when
we flip `ENCRYPTION_PROVIDER=aesgcm` on stage 7, no service code changes.
"""

from __future__ import annotations

import structlog

from app.services.encryption_service import EncryptionService

log = structlog.get_logger(__name__)

# Ровно 32 байта — на этапе 7 настоящий мастер-ключ Argon2id даёт столько же.
_IDENTITY_STUB_KEY: bytes = b"identity-stub-key-32-bytes-pad!!"
assert len(_IDENTITY_STUB_KEY) == 32, "identity stub key must be exactly 32 bytes"


class IdentityEncryptionService(EncryptionService):
    """Passthrough implementation — every method is a no-op."""

    async def encrypt(self, plaintext: str, user_id: int) -> str:
        log.debug("encryption.identity.encrypt", user_id=user_id, length=len(plaintext))
        return plaintext

    async def decrypt(self, ciphertext: str, user_id: int) -> str:
        log.debug("encryption.identity.decrypt", user_id=user_id, length=len(ciphertext))
        return ciphertext

    async def derive_user_key(self, password: str, salt: bytes) -> bytes:
        log.debug("encryption.identity.derive_user_key", salt_len=len(salt))
        return _IDENTITY_STUB_KEY

    async def store_session_key(
        self,
        user_id: int,
        session_id: str,
        key: bytes,
        ttl_seconds: int,
    ) -> None:
        log.debug(
            "encryption.identity.store_session_key",
            user_id=user_id,
            session_id=session_id,
            ttl_seconds=ttl_seconds,
        )

    async def get_session_key(self, user_id: int, session_id: str) -> bytes | None:
        # В identity-режиме ключ «есть всегда» — это упрощает тесты сервисов,
        # которые на этапе 7 будут зависеть от живой сессии.
        log.debug(
            "encryption.identity.get_session_key",
            user_id=user_id,
            session_id=session_id,
        )
        return _IDENTITY_STUB_KEY

    async def revoke_session_key(self, user_id: int, session_id: str) -> None:
        log.debug(
            "encryption.identity.revoke_session_key",
            user_id=user_id,
            session_id=session_id,
        )

    async def encrypt_with_key(self, plaintext: str, key: bytes) -> str:
        log.debug("encryption.identity.encrypt_with_key", length=len(plaintext))
        return plaintext

    async def decrypt_with_key(self, ciphertext: str, key: bytes) -> str:
        log.debug("encryption.identity.decrypt_with_key", length=len(ciphertext))
        return ciphertext
