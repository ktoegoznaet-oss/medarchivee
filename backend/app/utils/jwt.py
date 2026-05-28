"""JWT helpers for access tokens.

Refresh tokens are NOT JWTs — they are random UUID4 values with SHA-256 hashes
stored in `user_sessions` so we can revoke them. See `app/services/auth_service.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from app.config import settings


class InvalidTokenError(Exception):
    """Raised when a JWT fails decoding or validation."""


def create_access_token(user_id: int, role: str) -> str:
    """Build a signed access JWT.

    Payload: `sub`, `role`, `iat`, `exp`, `type='access'`.
    """
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(
            (now + timedelta(minutes=settings.jwt_access_token_expire_minutes)).timestamp()
        ),
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode + validate an access JWT. Raises :class:`InvalidTokenError` on failure."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.PyJWTError as exc:
        raise InvalidTokenError(str(exc)) from exc
    if payload.get("type") != "access":
        raise InvalidTokenError("Wrong token type")
    return payload
