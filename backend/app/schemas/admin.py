"""Admin API schemas — invites, system settings."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import UserRole, UserStatus
from app.services.invite_service import InviteStatus
from app.services.system_settings_service import RegistrationMode


class _BaseModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)


# ---- Invites --------------------------------------------------------- #


class InviteCreateRequest(_BaseModel):
    note: str | None = Field(default=None, max_length=255)


class InviteOut(_BaseModel):
    id: int
    code: str
    created_by_admin_id: int
    created_at: datetime
    expires_at: datetime
    used_by_user_id: int | None = None
    used_by_email: EmailStr | None = None
    used_at: datetime | None = None
    revoked_at: datetime | None = None
    note: str | None = None
    status: InviteStatus


class InviteCreateResponse(_BaseModel):
    invite: InviteOut


class InviteListResponse(_BaseModel):
    invites: list[InviteOut]


# ---- System settings ------------------------------------------------- #


class RegistrationModeOut(_BaseModel):
    mode: RegistrationMode


class RegistrationModeUpdate(_BaseModel):
    mode: RegistrationMode


# ---- Dashboard ------------------------------------------------------- #


class DailyCountOut(_BaseModel):
    date: str
    count: int


class DashboardStatsOut(_BaseModel):
    users_total: int
    users_active_7d: int
    users_active_30d: int
    users_blocked: int
    users_new_7d: int
    tickets_total: int
    tickets_new: int
    uploads_size_bytes: int
    activity_by_day: list[DailyCountOut]


# ---- Users management ------------------------------------------------ #


class AdminUserOut(_BaseModel):
    id: int
    email: EmailStr
    username: str
    role: UserRole
    status: UserStatus
    email_verified: bool
    recovery_phrase_set: bool
    created_at: datetime
    last_login_at: datetime | None = None


class UserListResponse(_BaseModel):
    users: list[AdminUserOut]
    total: int


class SetUserStatusRequest(_BaseModel):
    status: UserStatus


class SetUserRoleRequest(_BaseModel):
    role: UserRole


# ---- System limits --------------------------------------------------- #


class SystemLimitsOut(_BaseModel):
    ai_daily_limit: int
    user_quota_bytes: int


class SystemLimitsUpdate(_BaseModel):
    ai_daily_limit: int | None = Field(default=None, ge=0, le=10_000)
    user_quota_bytes: int | None = Field(default=None, ge=0)
