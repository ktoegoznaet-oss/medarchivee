"""bcrypt-based password hashing.

bcrypt is used only for authenticating users (login). The encryption master
key is derived separately via Argon2id (см. `docs/ENCRYPTION.md`).
"""

from __future__ import annotations

from passlib.context import CryptContext

# ~250 ms на хеш в типичной dev-машине. Намеренно дорого для защиты от брутфорса.
_pwd_context = CryptContext(schemes=["bcrypt"], bcrypt__rounds=12, deprecated="auto")


def hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return _pwd_context.verify(password, password_hash)
