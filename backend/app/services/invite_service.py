"""InviteService — генерация, проверка, потребление и отзыв инвайт-кодов.

Формат кода: 26 символов base32 от 16-байтного CSPRNG-сида.
Алфавит base32 — без `0`, `O`, `1`, `I`-подобных символов, легко
надиктовать. Энтропия ~80 бит (16 байт), что хорошо защищает от
угадывания при rate-limit на регистрацию.

Жизненный цикл:
  create → потенциально used (один раз) | revoked | expired (по времени)

Срок жизни — 7 дней по ТЗ. После использования кода у пользователя
данные сохраняются неограниченно — код больше не проверяется.
"""

from __future__ import annotations

import base64
import secrets
from datetime import UTC, datetime, timedelta
from enum import Enum

import structlog
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.invite import InviteCode

log = structlog.get_logger(__name__)

_INVITE_TTL = timedelta(days=7)
_INVITE_CODE_BYTES = 16  # → base32-26-символьный код


class InviteStatus(str, Enum):
    ACTIVE = "active"
    USED = "used"
    REVOKED = "revoked"
    EXPIRED = "expired"


class InviteCodeNotFoundError(Exception):
    pass


class InviteCodeInvalidError(Exception):
    """Код не найден, истёк, отозван или уже использован."""


class InviteCodeAlreadyUsedError(Exception):
    pass


def _generate_invite_code() -> str:
    """26-символьный base32-код от 16 CSPRNG-байт.

    Использует стандартный base32 RFC 4648 (без padding `=`), uppercase.
    Энтропия — 16 × 8 = 128 бит, фактическая длина строки — 26 символов.
    """
    raw = secrets.token_bytes(_INVITE_CODE_BYTES)
    return base64.b32encode(raw).decode("ascii").rstrip("=")


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _classify(invite: InviteCode, now: datetime) -> InviteStatus:
    if invite.used_by_user_id is not None:
        return InviteStatus.USED
    if invite.revoked_at is not None:
        return InviteStatus.REVOKED
    if invite.expires_at < now:
        return InviteStatus.EXPIRED
    return InviteStatus.ACTIVE


class InviteService:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def create_code(
        self, *, admin_id: int, note: str | None = None
    ) -> InviteCode:
        # Маловероятный, но возможный case collision на коротких кодах —
        # перегенерируем при конфликте по уникальному индексу.
        for attempt in range(5):
            code = _generate_invite_code()
            existing = await self._db.execute(
                select(InviteCode).where(InviteCode.code == code)
            )
            if existing.scalar_one_or_none() is None:
                break
            log.warning("invite.code_collision", attempt=attempt)
        else:
            # Крайне маловероятно при 80-bit entropy, но fail-fast лучше cycle.
            raise RuntimeError(
                "Failed to generate unique invite code after 5 attempts"
            )

        invite = InviteCode(
            code=code,
            created_by_admin_id=admin_id,
            expires_at=_now() + _INVITE_TTL,
            note=note,
        )
        self._db.add(invite)
        await self._db.commit()
        await self._db.refresh(invite)
        log.info(
            "invite.created",
            invite_id=invite.id,
            admin_id=admin_id,
            expires_at=invite.expires_at.isoformat(),
        )
        return invite

    async def list_codes(self) -> list[tuple[InviteCode, InviteStatus]]:
        """Все коды, отсортированные по дате создания (новые сверху).

        Возвращает пары (invite, статус) — статус вычисляется на лету,
        в БД не материализуется (expired считается лениво).
        """
        rows = await self._db.execute(
            select(InviteCode).order_by(desc(InviteCode.created_at))
        )
        now = _now()
        return [(inv, _classify(inv, now)) for inv in rows.scalars()]

    async def revoke(self, invite_id: int) -> InviteCode:
        invite = await self._db.get(InviteCode, invite_id)
        if invite is None:
            raise InviteCodeNotFoundError()
        if invite.used_by_user_id is not None:
            raise InviteCodeAlreadyUsedError()
        if invite.revoked_at is None:
            invite.revoked_at = _now()
            await self._db.commit()
            await self._db.refresh(invite)
            log.info("invite.revoked", invite_id=invite.id)
        return invite

    async def consume(self, *, code: str, user_id: int) -> InviteCode:
        """Атомарно использует код регистрацией пользователя.

        Поднимает InviteCodeInvalidError, если код не найден, истёк,
        отозван или уже использован. После успеха код больше нельзя
        переиспользовать.
        """
        result = await self._db.execute(
            select(InviteCode).where(InviteCode.code == code)
        )
        invite = result.scalar_one_or_none()
        if invite is None:
            raise InviteCodeInvalidError("invite_not_found")

        now = _now()
        status = _classify(invite, now)
        if status != InviteStatus.ACTIVE:
            raise InviteCodeInvalidError(f"invite_{status.value}")

        invite.used_by_user_id = user_id
        invite.used_at = now
        await self._db.flush()
        log.info(
            "invite.consumed",
            invite_id=invite.id,
            user_id=user_id,
        )
        return invite
