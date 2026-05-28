"""Pydantic schemas for /api/v1/telegram/*."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class _BaseModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)


class TelegramBindingStatus(_BaseModel):
    bound: bool
    telegram_user_id: int | None = None
    telegram_username: str | None = None
    bound_at: datetime | None = None
    notifications_enabled: bool = True
    notify_medications: bool = True
    notify_visits: bool = True
    notify_daily_summary: bool = False
    notify_health_tips: bool = False


class TelegramBindingCodeResponse(_BaseModel):
    code: str
    expires_at: datetime
    bot_username: str
    deep_link: str


class TelegramNotificationSettingsUpdate(_BaseModel):
    notifications_enabled: bool | None = None
    notify_medications: bool | None = None
    notify_visits: bool | None = None
    notify_daily_summary: bool | None = None
    notify_health_tips: bool | None = None


class TelegramTestMessageResponse(_BaseModel):
    delivered: bool
