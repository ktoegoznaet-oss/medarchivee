"""Schemas for /api/v1/recovery/* — BIP39 phrase management + reset password."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.services.password_validator import validate_password_strength
from app.services.recovery_service import RecoveryLanguage


class _BaseModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)


class GeneratePhraseRequest(_BaseModel):
    lang: RecoveryLanguage = RecoveryLanguage.RUSSIAN


class GeneratePhraseResponse(_BaseModel):
    phrase: str  # 12 words separated by spaces
    lang: RecoveryLanguage
    # Индексы для подтверждения сохранения (0-based, 3 случайных позиции).
    confirmation_indices: list[int]


class ConfirmPhraseRequest(_BaseModel):
    phrase: str = Field(min_length=10, max_length=400)
    lang: RecoveryLanguage = RecoveryLanguage.RUSSIAN
    confirmation_indices: list[int] = Field(min_length=3, max_length=3)
    confirmation_words: list[str] = Field(min_length=3, max_length=3)


class RegeneratePhraseRequest(_BaseModel):
    password: str = Field(min_length=1, max_length=200)


class PhraseStatusResponse(_BaseModel):
    recovery_phrase_set: bool
    lang: RecoveryLanguage | None = None


class ResetPasswordRequest(_BaseModel):
    email: EmailStr
    phrase: str = Field(min_length=10, max_length=400)
    new_password: str = Field(min_length=1, max_length=200)
    new_password_confirm: str

    @model_validator(mode="after")
    def _check(self) -> "ResetPasswordRequest":
        if self.new_password != self.new_password_confirm:
            raise ValueError("password_mismatch")
        errors = validate_password_strength(self.new_password, email=self.email)
        if errors:
            raise ValueError(",".join(errors))
        return self


class WipeAccountRequest(_BaseModel):
    email: EmailStr


class ConfirmWipeRequest(_BaseModel):
    email: EmailStr
    code: str = Field(min_length=8, max_length=8, pattern=r"^\d{8}$")


class MessageResponse(_BaseModel):
    message: str
