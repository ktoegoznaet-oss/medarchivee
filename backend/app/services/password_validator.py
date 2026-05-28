"""Password strength validation — shared between Pydantic schema and tests.

Rules per ТЗ §3.1 and stage-2 prompt §2.5:
  - длина ≥ 12
  - есть заглавная, строчная, цифра, спецсимвол
  - не совпадает с email/username (case-insensitive)
"""

from __future__ import annotations

import re

_MIN_LENGTH = 12
_UPPERCASE_RE = re.compile(r"[A-Z]")
_LOWERCASE_RE = re.compile(r"[a-z]")
_DIGIT_RE = re.compile(r"[0-9]")
_SPECIAL_RE = re.compile(r"""[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>/?`~]""")


def validate_password_strength(
    password: str,
    *,
    email: str | None = None,
    username: str | None = None,
) -> list[str]:
    """Return list of validation error codes; empty list means «valid»."""
    errors: list[str] = []

    if len(password) < _MIN_LENGTH:
        errors.append("password_too_short")
    if not _UPPERCASE_RE.search(password):
        errors.append("password_missing_uppercase")
    if not _LOWERCASE_RE.search(password):
        errors.append("password_missing_lowercase")
    if not _DIGIT_RE.search(password):
        errors.append("password_missing_digit")
    if not _SPECIAL_RE.search(password):
        errors.append("password_missing_special")

    pwd_lower = password.lower()
    if email and email.lower() in pwd_lower:
        errors.append("password_matches_email")
    if username and username.lower() in pwd_lower:
        errors.append("password_matches_username")

    return errors
