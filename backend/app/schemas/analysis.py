"""Pydantic schemas for /api/v1/analyses/*."""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.analysis import AbnormalType


class _BaseModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)


# ---------- Values --------------------------------------------------------- #


class AnalysisValueInput(_BaseModel):
    parameter_code: str | None = Field(default=None, max_length=50)
    parameter_name: str = Field(min_length=1, max_length=200)
    value: str = Field(min_length=1, max_length=100)
    unit: str = Field(min_length=1, max_length=50)
    reference_min: str | None = Field(default=None, max_length=50)
    reference_max: str | None = Field(default=None, max_length=50)


class AnalysisValueResponse(_BaseModel):
    id: int
    record_id: int
    user_id: int
    parameter_code: str | None = None
    parameter_name: str
    value: str
    unit: str
    reference_min: str | None
    reference_max: str | None
    is_abnormal: bool
    abnormal_type: AbnormalType


class AnalysisValueUpdate(_BaseModel):
    value: str | None = Field(default=None, min_length=1, max_length=100)
    unit: str | None = Field(default=None, min_length=1, max_length=50)
    reference_min: str | None = Field(default=None, max_length=50)
    reference_max: str | None = Field(default=None, max_length=50)
    parameter_name: str | None = Field(default=None, min_length=1, max_length=200)


# ---------- Records -------------------------------------------------------- #


class AnalysisRecordCreate(_BaseModel):
    analysis_date: date
    lab_name: str | None = Field(default=None, max_length=200)
    doctor_referral: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=2000)
    values: list[AnalysisValueInput] = Field(default_factory=list)


class AnalysisRecordUpdate(_BaseModel):
    lab_name: str | None = Field(default=None, max_length=200)
    doctor_referral: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=2000)
    analysis_date: date | None = None


class AnalysisRecordSummary(_BaseModel):
    id: int
    user_id: int
    analysis_date: date
    lab_name: str | None
    values_count: int
    abnormal_count: int


class AnalysisRecordFull(_BaseModel):
    id: int
    user_id: int
    analysis_date: date
    lab_name: str | None
    doctor_referral: str | None
    notes: str | None
    created_at: datetime
    values: list[AnalysisValueResponse]


# ---------- Parameter history (chart) ------------------------------------- #


class AnalysisHistoryPoint(_BaseModel):
    analysis_date: date
    value: str
    value_numeric: float | None
    unit: str
    reference_min: str | None
    reference_max: str | None
    is_abnormal: bool
    abnormal_type: AbnormalType


class AnalysisHistoryResponse(_BaseModel):
    parameter_code: str
    parameter_name: str | None
    unit: str | None
    points: list[AnalysisHistoryPoint]


# ---------- Dictionary ---------------------------------------------------- #


class AnalysisParameterSummary(_BaseModel):
    code: str
    name_ru: str
    unit: str
    category: str


class AnalysisParameterNorm(_BaseModel):
    min: float | None
    max: float | None
    gender: str
    age_from: int
    age_to: int


class AnalysisParameterDetail(_BaseModel):
    code: str
    name_ru: str
    name_en: str
    unit: str
    alternative_units: list[str]
    category: str
    description: str | None
    synonyms: list[str]
    applicable_norm: AnalysisParameterNorm | None
