"""Pydantic v2 schemas for /api/v1/auth/*.

Never expose `password_hash`, `encryption_salt`, `recovery_master_key`,
`recovery_code_hash`, or `two_factor_secret` — none of these belong in API
responses (see ТЗ §6 and stage-2 prompt §2.7).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.models.user import UserRole
from app.services.password_validator import validate_password_strength


class _BaseModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)


class RegisterRequest(_BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=100, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=1, max_length=200)
    password_confirm: str
    terms_accepted: bool
    privacy_accepted: bool
    medical_disclaimer_accepted: bool
    # Опциональное поле — обязательно в invite_only режиме, игнорируется в open.
    # Валидация принадлежности к режиму — на стороне сервиса, не схемы:
    # серверу нужно знать текущий registration_mode из БД.
    invite_code: str | None = Field(default=None, max_length=32)

    @model_validator(mode="after")
    def _check(self) -> RegisterRequest:
        if self.password != self.password_confirm:
            raise ValueError("password_mismatch")
        for flag, code in (
            (self.terms_accepted, "terms_required"),
            (self.privacy_accepted, "privacy_required"),
            (self.medical_disclaimer_accepted, "medical_disclaimer_required"),
        ):
            if not flag:
                raise ValueError(code)
        errors = validate_password_strength(
            self.password,
            email=self.email,
            username=self.username,
        )
        if errors:
            raise ValueError(",".join(errors))
        return self


class UserPublic(_BaseModel):
    """Safe-to-expose subset of `users` columns."""

    id: int
    email: EmailStr
    username: str
    role: UserRole
    email_verified: bool
    created_at: datetime


class RegisterResponse(_BaseModel):
    user: UserPublic
    message: str = "verification_code_sent"


class VerifyEmailRequest(_BaseModel):
    user_id: int
    code: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class VerifyEmailResponse(_BaseModel):
    user: UserPublic


class ResendVerificationRequest(_BaseModel):
    user_id: int


class LoginRequest(_BaseModel):
    email_or_username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=200)
    remember_me: bool = False


class TokenPair(_BaseModel):
    access_token: str
    token_type: str = "Bearer"


class LoginResponse(_BaseModel):
    access_token: str
    token_type: str = "Bearer"
    user: UserPublic


class RefreshResponse(_BaseModel):
    access_token: str
    token_type: str = "Bearer"


class MessageResponse(_BaseModel):
    message: str


class RegistrationModePublicResponse(_BaseModel):
    """Публичный эндпоинт — фронт читает чтобы знать, показывать ли поле invite."""

    mode: str
