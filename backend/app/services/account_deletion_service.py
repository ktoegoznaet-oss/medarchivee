"""AccountDeletionService — удаление аккаунта аутентифицированным пользователем.

Отличается от RecoveryService.confirm_wipe (см. Шаг F) тем, что здесь
пользователь уже залогинен и подтверждает паролем. Wipe-flow же был
для случая «забыл и пароль и фразу» — там подтверждение через email-код.

После удаления:
  * CASCADE FK сносят профиль, анализы, AI, тикеты в БД
  * Файлы пользователя (скриншоты тикетов) удаляются с диска вручную
  * DEK в Redis_keys остаётся, но истечёт по TTL — не важно
"""

from __future__ import annotations

import shutil
from pathlib import Path

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.support import SupportTicket
from app.models.user import User
from app.services.admin_telegram.notifier import AdminNotifierProtocol
from app.utils.passwords import verify_password

log = structlog.get_logger(__name__)


class WrongPasswordError(Exception):
    pass


class AccountDeletionService:
    def __init__(
        self,
        db: AsyncSession,
        uploads_root: Path,
        admin_notifier: AdminNotifierProtocol,
    ):
        self._db = db
        self._uploads_root = uploads_root
        self._admin_notifier = admin_notifier

    async def delete(self, *, user: User, password: str) -> None:
        if not verify_password(password, user.password_hash):
            raise WrongPasswordError()

        # Сначала собрать список ticket_id (нужно для удаления uploads-
        # директорий ПОСЛЕ commit). До commit БД-rows ещё на месте,
        # запрос отработает корректно.
        tickets_result = await self._db.execute(
            select(SupportTicket.id).where(SupportTicket.user_id == user.id)
        )
        ticket_ids = list(tickets_result.scalars())
        email = user.email  # сохранить до удаления для уведомления

        # Commit перед удалением файлов. Если commit упадёт (FK conflict,
        # DB lost connection) — файлы остаются на диске, юзер остаётся
        # в БД, всё консистентно. Если бы порядок был обратным, могли
        # потерять файлы без удаления юзера → 500 при следующем доступе
        # к тикетам.
        await self._db.delete(user)
        await self._db.commit()

        # Теперь юзер удалён — cascade FK снесли support_tickets и
        # ticket_attachments rows. Удаляем orphaned директории.
        # Если что-то падает на этом этапе — лог, но не ошибка для клиента:
        # юзер уже удалён, главное действие выполнено.
        for ticket_id in ticket_ids:
            ticket_dir = self._uploads_root / "tickets" / str(ticket_id)
            if ticket_dir.exists():
                try:
                    shutil.rmtree(ticket_dir, ignore_errors=True)
                except OSError as exc:
                    log.warning(
                        "account.uploads_cleanup_failed",
                        user_email=email,
                        ticket_id=ticket_id,
                        error=str(exc),
                    )

        log.info("account.self_deleted", user_email=email)
        await self._admin_notifier.notify(
            f"🗑 Пользователь <code>{email}</code> удалил свой аккаунт."
        )
