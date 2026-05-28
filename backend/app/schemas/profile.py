"""Pydantic v2 schemas for the patient profile module.

Notes on shape:
  * Numbers (`height_cm`, `weight_kg`) are typed as `float` in API contracts.
    The ORM stores them as encrypted `Text`; conversion happens in the service.
  * `birth_date` is exposed as an ISO `date`; storage uses an encrypted string.
  * `timezone` is validated against the IANA database (`zoneinfo`).
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.patient_profile import AllergySeverity


class Gender(str, Enum):
    MALE = "male"
    FEMALE = "female"
    NOT_SPECIFIED = "not_specified"


_MIN_BIRTH = date(1900, 1, 1)


class _BaseModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)


# ---------- Profile -------------------------------------------------------- #


class PatientProfileBase(_BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    middle_name: str | None = Field(default=None, max_length=100)
    birth_date: date
    gender: Gender
    blood_type: str | None = Field(default=None, max_length=3)
    height_cm: float | None = Field(default=None, ge=30, le=250)
    weight_kg: float | None = Field(default=None, ge=1, le=500)
    emergency_contact: str | None = Field(default=None, max_length=500)
    insurance_info: str | None = Field(default=None, max_length=500)
    city: str | None = Field(default=None, max_length=100)
    timezone: str = Field(default="Europe/Moscow", max_length=50)

    @field_validator("birth_date")
    @classmethod
    def _check_birth_range(cls, value: date) -> date:
        if value < _MIN_BIRTH:
            raise ValueError("birth_date_before_1900")
        if value > date.today():
            raise ValueError("birth_date_in_future")
        return value

    @field_validator("timezone")
    @classmethod
    def _check_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("invalid_timezone") from exc
        return value

    @field_validator("blood_type")
    @classmethod
    def _check_blood_type(cls, value: str | None) -> str | None:
        if value is None:
            return None
        allowed = {"O+", "O-", "A+", "A-", "B+", "B-", "AB+", "AB-"}
        if value not in allowed:
            raise ValueError("invalid_blood_type")
        return value


class PatientProfileCreate(PatientProfileBase):
    pass


class PatientProfileUpdate(_BaseModel):
    """Все поля опциональны — частичное обновление."""

    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    middle_name: str | None = Field(default=None, max_length=100)
    birth_date: date | None = None
    gender: Gender | None = None
    blood_type: str | None = Field(default=None, max_length=3)
    height_cm: float | None = Field(default=None, ge=30, le=250)
    weight_kg: float | None = Field(default=None, ge=1, le=500)
    emergency_contact: str | None = Field(default=None, max_length=500)
    insurance_info: str | None = Field(default=None, max_length=500)
    city: str | None = Field(default=None, max_length=100)
    timezone: str | None = Field(default=None, max_length=50)

    @field_validator("birth_date")
    @classmethod
    def _check_birth_range(cls, value: date | None) -> date | None:
        if value is None:
            return None
        if value < _MIN_BIRTH:
            raise ValueError("birth_date_before_1900")
        if value > date.today():
            raise ValueError("birth_date_in_future")
        return value

    @field_validator("timezone")
    @classmethod
    def _check_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("invalid_timezone") from exc
        return value


class PatientProfileResponse(PatientProfileBase):
    id: int
    user_id: int
    updated_at: datetime


# ---------- Weight history ------------------------------------------------- #


class WeightRecordCreate(_BaseModel):
    weight_kg: float = Field(ge=1, le=500)
    note: str | None = Field(default=None, max_length=500)


class WeightRecordResponse(_BaseModel):
    id: int
    user_id: int
    weight_kg: float
    note: str | None
    recorded_at: datetime


# ---------- Chronic conditions -------------------------------------------- #


class ChronicConditionCreate(_BaseModel):
    name: str = Field(min_length=1, max_length=200)
    icd10_code: str | None = Field(default=None, max_length=10)
    diagnosed_at: date | None = None
    note: str | None = Field(default=None, max_length=2000)
    is_active: bool = True


class ChronicConditionUpdate(_BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    icd10_code: str | None = Field(default=None, max_length=10)
    diagnosed_at: date | None = None
    note: str | None = Field(default=None, max_length=2000)
    is_active: bool | None = None


class ChronicConditionResponse(_BaseModel):
    id: int
    user_id: int
    name: str
    icd10_code: str | None
    diagnosed_at: date | None
    note: str | None
    is_active: bool
    created_at: datetime


# ---------- Allergies ----------------------------------------------------- #


class AllergyCreate(_BaseModel):
    allergen: str = Field(min_length=1, max_length=200)
    reaction: str | None = Field(default=None, max_length=500)
    note: str | None = Field(default=None, max_length=2000)
    severity: AllergySeverity = AllergySeverity.MILD


class AllergyUpdate(_BaseModel):
    allergen: str | None = Field(default=None, min_length=1, max_length=200)
    reaction: str | None = Field(default=None, max_length=500)
    note: str | None = Field(default=None, max_length=2000)
    severity: AllergySeverity | None = None


class AllergyResponse(_BaseModel):
    id: int
    user_id: int
    allergen: str
    reaction: str | None
    note: str | None
    severity: AllergySeverity
    created_at: datetime


# ---------- Family history ------------------------------------------------ #


class FamilyHistoryCreate(_BaseModel):
    relation: str = Field(min_length=1, max_length=100)
    condition: str = Field(min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=2000)


class FamilyHistoryUpdate(_BaseModel):
    relation: str | None = Field(default=None, min_length=1, max_length=100)
    condition: str | None = Field(default=None, min_length=1, max_length=200)
    note: str | None = Field(default=None, max_length=2000)


class FamilyHistoryResponse(_BaseModel):
    id: int
    user_id: int
    relation: str
    condition: str
    note: str | None
    created_at: datetime


# ---------- Dictionary ---------------------------------------------------- #


class ICD10Entry(_BaseModel):
    code: str
    name: str
