"""Abstract encryption service contract.

This file defines the boundary between business logic and the actual crypto
implementation. Every service that handles 🔒-fields (per spec §5) must depend
on `EncryptionService` — never on a concrete implementation — so that we can
swap the identity stub (stages 1–6) for AES-256-GCM (stage 7+) by flipping
`ENCRYPTION_PROVIDER` in `.env`.

See `docs/ENCRYPTION.md` for the full strategy.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class EncryptionError(Exception):
    """Base class for encryption subsystem errors."""


class SessionKeyNotFoundError(EncryptionError):
    """Raised when a user's master key is not present in `redis_keys`.

    On stage 7 this typically means the refresh-token TTL expired and the user
    has to log in again. On identity stage it is never raised.
    """


class EncryptionService(ABC):
    """Service contract for per-user data encryption.

    Implementations:
      * `IdentityEncryptionService` — passthrough stub (stages 1–6).
      * `AESGCMEncryptionService`   — AES-256-GCM with Argon2id KDF (stage 7+).

    All methods take a `user_id` because the master key is derived from
    that user's password — different users have different keys.
    """

    @abstractmethod
    async def encrypt(self, plaintext: str, user_id: int) -> str:
        """Encrypt a string for a specific user.

        Args:
            plaintext: original text (empty string is allowed).
            user_id: owner of the data — determines which master key is used.

        Returns:
            base64-encoded ciphertext in the AES implementation, or the
            original `plaintext` in the identity implementation.

        Raises:
            SessionKeyNotFoundError: if the user's session key is gone (stage 7+).
        """

    @abstractmethod
    async def decrypt(self, ciphertext: str, user_id: int) -> str:
        """Decrypt a string previously encrypted for the same user."""

    @abstractmethod
    async def derive_user_key(self, password: str, salt: bytes) -> bytes:
        """Derive a 32-byte master key from `password` + `salt`.

        Identity implementation returns a deterministic constant; AES
        implementation uses Argon2id.
        """

    @abstractmethod
    async def store_session_key(
        self,
        user_id: int,
        session_id: str,
        key: bytes,
        ttl_seconds: int,
    ) -> None:
        """Put the user's master key into `redis_keys` for the session lifetime.

        Identity implementation is a no-op.
        """

    @abstractmethod
    async def get_session_key(self, user_id: int, session_id: str) -> bytes | None:
        """Return the user's master key, or `None` if it has expired / is missing."""

    @abstractmethod
    async def revoke_session_key(self, user_id: int, session_id: str) -> None:
        """Drop the user's master key from `redis_keys` (called on logout)."""

    @abstractmethod
    async def encrypt_with_key(self, plaintext: str, key: bytes) -> str:
        """Encrypt with an explicit key (no session lookup).

        Used to encrypt the master key with a key derived from the recovery
        code, producing `users.recovery_master_key`.
        """

    @abstractmethod
    async def decrypt_with_key(self, ciphertext: str, key: bytes) -> str:
        """Inverse of :meth:`encrypt_with_key`."""
