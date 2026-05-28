"""SystemSettingsService — централизованное хранение редактируемых настроек.

Сейчас используется только для `registration_mode`. На Этапе 9 туда же
попадут лимиты rate-limiting и квот.

Хранение — таблица `system_settings (key, value)`. Кэширование в памяти
process'а (TTL 60 секунд) — частые чтения `registration_mode` не должны
бить по БД на каждом запросе регистрации. Кэш сбрасывается при `set_value`.
"""

from __future__ import annotations

import time
from enum import Enum

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.system_setting import SystemSetting

log = structlog.get_logger(__name__)

REGISTRATION_MODE_KEY = "registration_mode"
# Daily AI requests per user
AI_DAILY_LIMIT_KEY = "ai_daily_limit"
AI_DAILY_LIMIT_DEFAULT = 50
# Max bytes per user upload (cumulative, future use in Шаг K)
USER_QUOTA_BYTES_KEY = "user_quota_bytes"
USER_QUOTA_BYTES_DEFAULT = 500 * 1024 * 1024  # 500 MB

_CACHE_TTL_SECONDS = 60


class RegistrationMode(str, Enum):
    CLOSED = "closed"
    INVITE_ONLY = "invite_only"
    OPEN = "open"


class UnknownSettingError(Exception):
    pass


class SystemSettingsService:
    _cache: dict[str, tuple[float, str]] = {}

    def __init__(self, db: AsyncSession):
        self._db = db

    async def get_value(self, key: str, default: str | None = None) -> str | None:
        cached = self._cache.get(key)
        if cached is not None:
            expires_at, value = cached
            if expires_at > time.monotonic():
                return value

        row = await self._db.get(SystemSetting, key)
        if row is None:
            return default
        self._cache[key] = (time.monotonic() + _CACHE_TTL_SECONDS, row.value)
        return row.value

    async def set_value(
        self,
        key: str,
        value: str,
        *,
        updated_by_user_id: int | None,
    ) -> None:
        existing = await self._db.get(SystemSetting, key)
        if existing is None:
            setting = SystemSetting(
                key=key, value=value, updated_by_user_id=updated_by_user_id
            )
            self._db.add(setting)
        else:
            existing.value = value
            existing.updated_by_user_id = updated_by_user_id
        await self._db.commit()
        self._cache.pop(key, None)
        log.info(
            "system_settings.updated",
            key=key,
            value=value,
            updated_by_user_id=updated_by_user_id,
        )

    async def get_registration_mode(self) -> RegistrationMode:
        value = await self.get_value(REGISTRATION_MODE_KEY, default="invite_only")
        try:
            return RegistrationMode(value)
        except ValueError:
            log.warning("system_settings.invalid_registration_mode", value=value)
            return RegistrationMode.INVITE_ONLY

    async def set_registration_mode(
        self, mode: RegistrationMode, *, updated_by_user_id: int
    ) -> None:
        await self.set_value(
            REGISTRATION_MODE_KEY,
            mode.value,
            updated_by_user_id=updated_by_user_id,
        )

    async def get_int_setting(self, key: str, default: int) -> int:
        value = await self.get_value(key)
        if value is None:
            return default
        try:
            return int(value)
        except (TypeError, ValueError):
            log.warning("system_settings.invalid_int", key=key, value=value)
            return default

    async def get_ai_daily_limit(self) -> int:
        return await self.get_int_setting(
            AI_DAILY_LIMIT_KEY, AI_DAILY_LIMIT_DEFAULT
        )

    async def get_user_quota_bytes(self) -> int:
        return await self.get_int_setting(
            USER_QUOTA_BYTES_KEY, USER_QUOTA_BYTES_DEFAULT
        )

    @classmethod
    def clear_cache(cls) -> None:
        """Test helper — сбрасывает межтестовое состояние кэша."""
        cls._cache.clear()
