"""Telegram bot binding service.

Покрывает §9.2 ТЗ v1.1 на этапе 6:
  * генерация 6-значного кода привязки (TTL 10 мин, инвалидация старых);
  * привязка по коду (использует и backend через test, и бот через `/start КОД`);
  * статус привязки / настройки уведомлений / отвязка;
  * тестовое сообщение через `TelegramSender`.

Контракт изоляции: каждый метод принимает `user_id` и фильтрует им
запросы — пользователь A не может прочитать/изменить привязку B.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.telegram import TelegramBinding, TelegramBindingCode
from app.models.user import User
from app.schemas.telegram import TelegramNotificationSettingsUpdate
from app.services.telegram_sender import TelegramSender

log = structlog.get_logger(__name__)


# ---------- Constants ----------------------------------------------------- #

BINDING_CODE_TTL = timedelta(minutes=10)
# Не больше 3 валидных кодов в минуту с одного user_id — антиспам.
CODE_RATE_LIMIT_WINDOW = timedelta(minutes=1)
CODE_RATE_LIMIT_MAX = 3


# ---------- Exceptions ---------------------------------------------------- #


class TelegramError(Exception):
    """Base class for telegram-service errors."""


class BindingNotFoundError(TelegramError):
    pass


class BindingAlreadyExistsError(TelegramError):
    """Telegram-аккаунт уже привязан к другому пользователю."""


class BindingCodeInvalidError(TelegramError):
    pass


class BindingCodeExpiredError(TelegramError):
    pass


class CodeRateLimitError(TelegramError):
    """Слишком частая генерация кодов привязки."""


# ---------- DTO ----------------------------------------------------------- #


@dataclass(frozen=True)
class GeneratedCode:
    code: str
    expires_at: datetime


@dataclass(frozen=True)
class BindResult:
    ok: bool
    binding: TelegramBinding | None = None
    error: str | None = None


# ---------- Service ------------------------------------------------------- #


class TelegramService:
    def __init__(
        self,
        db: AsyncSession,
        sender: TelegramSender,
        *,
        bot_username: str,
    ) -> None:
        self._db = db
        self._sender = sender
        self._bot_username = bot_username

    # ---- Public surface --------------------------------------------------- #

    async def get_binding(self, user_id: int) -> TelegramBinding | None:
        return await self._fetch_binding(user_id)

    async def generate_binding_code(self, user_id: int) -> GeneratedCode:
        """Issue a new 6-digit code; invalidate previous unused ones."""
        now = datetime.now(UTC).replace(tzinfo=None)
        recent_cutoff = now - CODE_RATE_LIMIT_WINDOW
        recent_count = (
            await self._db.execute(
                select(TelegramBindingCode).where(
                    TelegramBindingCode.user_id == user_id,
                    TelegramBindingCode.created_at >= recent_cutoff,
                )
            )
        ).scalars().all()
        if len(recent_count) >= CODE_RATE_LIMIT_MAX:
            raise CodeRateLimitError(
                "Слишком много запросов. Попробуйте через минуту."
            )

        # Старые неиспользованные коды этого юзера — пометить used. Это и
        # rate-limit-friendly, и UX-friendly: один валидный код в каждый
        # момент времени, не путаемся.
        await self._db.execute(
            update(TelegramBindingCode)
            .where(
                TelegramBindingCode.user_id == user_id,
                TelegramBindingCode.used.is_(False),
            )
            .values(used=True)
        )

        code = await self._fresh_code()
        row = TelegramBindingCode(
            user_id=user_id,
            code=code,
            expires_at=now + BINDING_CODE_TTL,
        )
        self._db.add(row)
        await self._db.commit()
        log.info("telegram.code_generated", user_id=user_id)
        return GeneratedCode(code=row.code, expires_at=row.expires_at)

    async def bind_by_code(
        self,
        *,
        code: str,
        telegram_user_id: int,
        telegram_username: str | None,
    ) -> BindResult:
        """Consume a code and create the TelegramBinding.

        Использует и backend (для теста привязки в /unit/integration), и
        telegram_bot — отдельный сервис вызывает эту же логику через свою
        копию SQLAlchemy-моделей и через прямой UPDATE/INSERT (см.
        `telegram_bot/db/binding.py`). На backend-стороне здесь — основной
        источник истины.
        """
        normalized_username = (
            telegram_username.lstrip("@").lower() if telegram_username else None
        )
        row = (
            await self._db.execute(
                select(TelegramBindingCode).where(
                    TelegramBindingCode.code == code
                )
            )
        ).scalar_one_or_none()
        if row is None or row.used:
            return BindResult(ok=False, error="invalid_code")
        now = datetime.now(UTC).replace(tzinfo=None)
        if row.expires_at < now:
            return BindResult(ok=False, error="code_expired")

        existing = (
            await self._db.execute(
                select(TelegramBinding).where(
                    TelegramBinding.telegram_user_id == telegram_user_id
                )
            )
        ).scalar_one_or_none()
        if existing is not None and existing.user_id != row.user_id:
            return BindResult(ok=False, error="telegram_account_already_bound")

        # Если у пользователя уже была привязка к другому tg-id — заменим.
        # `existing` к этому моменту либо None, либо принадлежит этому же
        # пользователю (иначе вернули ошибку выше) — в обоих случаях нам
        # достаточно `own_binding`.
        own_binding = await self._fetch_binding(row.user_id)
        if own_binding is not None:
            own_binding.telegram_user_id = telegram_user_id
            own_binding.telegram_username = normalized_username
            binding = own_binding
        else:
            binding = TelegramBinding(
                user_id=row.user_id,
                telegram_user_id=telegram_user_id,
                telegram_username=normalized_username,
            )
            self._db.add(binding)

        row.used = True
        await self._db.commit()
        await self._db.refresh(binding)
        log.info(
            "telegram.bound",
            user_id=row.user_id,
            telegram_user_id=telegram_user_id,
        )
        return BindResult(ok=True, binding=binding)

    async def unbind(self, user_id: int) -> None:
        binding = await self._fetch_binding(user_id)
        if binding is None:
            raise BindingNotFoundError()
        await self._db.delete(binding)
        # Заодно почистим коды этого пользователя — чтобы случайный
        # старый код не привязал кого-то ещё.
        await self._db.execute(
            delete(TelegramBindingCode).where(
                TelegramBindingCode.user_id == user_id
            )
        )
        await self._db.commit()
        log.info("telegram.unbound", user_id=user_id)

    async def update_notification_settings(
        self, user_id: int, data: TelegramNotificationSettingsUpdate
    ) -> TelegramBinding:
        binding = await self._fetch_binding(user_id)
        if binding is None:
            raise BindingNotFoundError()
        updates = data.model_dump(exclude_unset=True)
        for field, value in updates.items():
            setattr(binding, field, value)
        await self._db.commit()
        await self._db.refresh(binding)
        log.info(
            "telegram.notification_settings_updated",
            user_id=user_id,
            fields=list(updates.keys()),
        )
        return binding

    async def send_test_message(self, user_id: int) -> bool:
        binding = await self._fetch_binding(user_id)
        if binding is None:
            raise BindingNotFoundError()
        now_local = datetime.now(UTC).strftime("%H:%M UTC")
        # Нейтральный текст — см. подсказку 6.5. Без чувствительных данных.
        text = (
            "Тестовое сообщение от МедАрхива. Если вы это видите — связь "
            f"работает. Сейчас {now_local}."
        )
        return await self._sender.send_message(binding.telegram_user_id, text)

    # ---- Helpers --------------------------------------------------------- #

    @property
    def bot_username(self) -> str:
        return self._bot_username

    def deep_link(self, code: str) -> str:
        return f"https://t.me/{self._bot_username}?start={code}"

    async def _fetch_binding(self, user_id: int) -> TelegramBinding | None:
        return (
            await self._db.execute(
                select(TelegramBinding).where(TelegramBinding.user_id == user_id)
            )
        ).scalar_one_or_none()

    async def _fresh_code(self) -> str:
        """Generate a 6-digit code that isn't already in use.

        Коллизии маловероятны (10^6 = 1М вариантов), но мы держим миллион
        одновременных активных кодов крайне навряд ли — поэтому одного-двух
        попыток хватает. Защита от бесконечного цикла — `max_attempts`.
        """
        max_attempts = 10
        for _ in range(max_attempts):
            code = f"{secrets.randbelow(1_000_000):06d}"
            exists = (
                await self._db.execute(
                    select(TelegramBindingCode).where(
                        TelegramBindingCode.code == code,
                        TelegramBindingCode.used.is_(False),
                    )
                )
            ).scalar_one_or_none()
            if exists is None:
                return code
        raise TelegramError("Could not allocate a unique binding code")


# ---------- Helpers re-exported for tests/handlers ------------------------- #


async def find_user_by_telegram_id(
    db: AsyncSession, telegram_user_id: int
) -> User | None:
    """Resolve User by their telegram_user_id (used by бот для /status)."""
    binding = (
        await db.execute(
            select(TelegramBinding).where(
                TelegramBinding.telegram_user_id == telegram_user_id
            )
        )
    ).scalar_one_or_none()
    if binding is None:
        return None
    return (
        await db.execute(select(User).where(User.id == binding.user_id))
    ).scalar_one_or_none()
