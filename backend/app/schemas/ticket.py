"""Pydantic-схемы для /api/v1/tickets/* и /api/v1/admin/tickets/*."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.support import TicketStatus, TicketType


class _BaseModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)


class CreateTicketRequest(_BaseModel):
    type: TicketType
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=5000)
    url: str | None = Field(default=None, max_length=500)
    user_agent: str | None = Field(default=None, max_length=500)
    screen_size: str | None = Field(default=None, max_length=20)


class TicketAttachmentOut(_BaseModel):
    id: int
    original_filename: str
    mime_type: str
    size_bytes: int
    created_at: datetime


class TicketCommentOut(_BaseModel):
    id: int
    ticket_id: int
    author_user_id: int
    body: str
    is_internal: bool
    created_at: datetime


class TicketOut(_BaseModel):
    id: int
    user_id: int
    user_email: EmailStr | None = None  # заполняется только в admin-эндпоинтах
    type: TicketType
    title: str
    description: str
    status: TicketStatus
    url: str | None = None
    user_agent: str | None = None
    screen_size: str | None = None
    created_at: datetime
    updated_at: datetime
    attachments: list[TicketAttachmentOut] = Field(default_factory=list)


class TicketDetailOut(TicketOut):
    comments: list[TicketCommentOut] = Field(default_factory=list)


class CreateCommentRequest(_BaseModel):
    body: str = Field(min_length=1, max_length=5000)


class AdminCreateCommentRequest(CreateCommentRequest):
    is_internal: bool = False


class UpdateStatusRequest(_BaseModel):
    status: TicketStatus


class TicketListResponse(_BaseModel):
    tickets: list[TicketOut]
