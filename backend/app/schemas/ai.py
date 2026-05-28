"""Pydantic schemas for /api/v1/ai/*."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.ai import (
    AIComplexity,
    AIDataAccessMode,
    AIMessageRole,
    AIProvider,
    AITone,
)


class _BaseModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)


# ---------- Settings ------------------------------------------------------ #


class AISettingsResponse(_BaseModel):
    id: int
    user_id: int
    preferred_provider: AIProvider
    complexity_level: AIComplexity
    tone: AITone
    data_access_mode: AIDataAccessMode
    created_at: datetime
    updated_at: datetime


class AISettingsUpdate(_BaseModel):
    preferred_provider: AIProvider | None = None
    complexity_level: AIComplexity | None = None
    tone: AITone | None = None
    data_access_mode: AIDataAccessMode | None = None


# ---------- Conversations ------------------------------------------------- #


class AIConversationSummary(_BaseModel):
    id: int
    title: str
    is_archived: bool
    created_at: datetime
    updated_at: datetime
    last_message_preview: str | None = None


class AIConversationFull(_BaseModel):
    id: int
    title: str
    is_archived: bool
    created_at: datetime
    updated_at: datetime


# ---------- Messages ------------------------------------------------------ #


class AttachedAnalysisDTO(_BaseModel):
    id: int
    analysis_date: str
    lab_name: str | None
    values: list[dict[str, object]]


class AttachedProfileDTO(_BaseModel):
    first_name: str
    last_name: str
    birth_date: str
    gender: str
    height_cm: str | None = None
    weight_kg: str | None = None
    blood_type: str | None = None
    city: str | None = None


class AttachedDataDTO(_BaseModel):
    """User-curated snapshot of data to share with the assistant.

    Mode «Ручной»: пользователь явно прикрепляет профиль и/или анализы.
    На этапе 5 — только эти две сущности; препараты/симптомы — позже.
    """

    include_profile: bool = False
    analysis_ids: list[int] = Field(default_factory=list)


class AIMessageDTO(_BaseModel):
    id: int
    conversation_id: int
    role: AIMessageRole
    content: str
    attached_data: AttachedDataDTO | None = None
    safety_event_type: str | None = None
    provider: str | None = None
    model: str | None = None
    tokens_used: int | None = None
    created_at: datetime


class AIMessageSendRequest(_BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    attached_data: AttachedDataDTO | None = None
    override_tone: AITone | None = None
    override_complexity: AIComplexity | None = None


class AIMessageSendResponse(_BaseModel):
    conversation: AIConversationFull
    user_message: AIMessageDTO
    assistant_message: AIMessageDTO
