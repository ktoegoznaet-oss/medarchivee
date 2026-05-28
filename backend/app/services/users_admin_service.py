"""UsersAdminService — операции админа над пользователями.

Что админ МОЖЕТ:
  * Видеть список с email/username/датой/статусом/ролью
  * Поиск по email/username
  * Блокировать (status=BLOCKED → не может логиниться)
  * Разблокировать (status=ACTIVE)
  * Назначить/снять роль ADMIN

Что админ НЕ МОЖЕТ:
  * Читать медданные (они зашифрованы DEK, KEK выводится из пароля)
  * Сбросить пароль другого (только сам пользователь через recovery-фразу)
  * Видеть encrypted_dek/recovery_master_key в API-ответе
  * Снять с себя role=ADMIN если он единственный админ (защита от
    блокировки админ-доступа)
"""

from __future__ import annotations

import structlog
from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, UserRole, UserStatus

log = structlog.get_logger(__name__)


class UserNotFoundError(Exception):
    pass


class SelfDemotionForbiddenError(Exception):
    """Нельзя снять админскую роль с последнего админа в системе."""


class CannotBlockSelfError(Exception):
    """Нельзя заблокировать самого себя — защита от случайной блокировки."""


class UsersAdminService:
    def __init__(self, db: AsyncSession):
        self._db = db

    async def list_users(
        self,
        *,
        search: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[User], int]:
        stmt = select(User).order_by(desc(User.created_at))
        count_stmt = select(func.count(User.id))

        if search:
            like = f"%{search.lower()}%"
            condition = or_(
                func.lower(User.email).like(like),
                func.lower(User.username).like(like),
            )
            stmt = stmt.where(condition)
            count_stmt = count_stmt.where(condition)

        total = (await self._db.execute(count_stmt)).scalar_one()
        users = list(
            (await self._db.execute(stmt.limit(limit).offset(offset)))
            .scalars()
        )
        return users, total

    async def get_user(self, user_id: int) -> User:
        user = await self._db.get(User, user_id)
        if user is None:
            raise UserNotFoundError()
        return user

    async def set_status(
        self,
        *,
        target_user_id: int,
        new_status: UserStatus,
        actor_user_id: int,
    ) -> User:
        if target_user_id == actor_user_id and new_status == UserStatus.BLOCKED:
            raise CannotBlockSelfError()
        user = await self.get_user(target_user_id)
        user.status = new_status
        await self._db.commit()
        await self._db.refresh(user)
        log.info(
            "admin.user_status_changed",
            target_user_id=target_user_id,
            new_status=new_status.value,
            actor_user_id=actor_user_id,
        )
        return user

    async def set_role(
        self,
        *,
        target_user_id: int,
        new_role: UserRole,
        actor_user_id: int,
    ) -> User:
        user = await self.get_user(target_user_id)
        if (
            new_role == UserRole.USER
            and user.role == UserRole.ADMIN
        ):
            admins_count = (
                await self._db.execute(
                    select(func.count(User.id)).where(User.role == UserRole.ADMIN)
                )
            ).scalar_one()
            if admins_count <= 1:
                raise SelfDemotionForbiddenError()
        user.role = new_role
        await self._db.commit()
        await self._db.refresh(user)
        log.info(
            "admin.user_role_changed",
            target_user_id=target_user_id,
            new_role=new_role.value,
            actor_user_id=actor_user_id,
        )
        return user
