"""Chronic conditions CRUD service.

Все запросы фильтруют по `user_id` — пользователь A не может ни прочитать,
ни обновить, ни удалить запись пользователя B (см. инвариант мастер-промпта §5.2).
"""

from __future__ import annotations

from datetime import date

import structlog
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.patient_profile import ChronicCondition
from app.schemas.profile import (
    ChronicConditionCreate,
    ChronicConditionResponse,
    ChronicConditionUpdate,
)
from app.services.encryption_service import EncryptionService

log = structlog.get_logger(__name__)


class ChronicConditionNotFoundError(Exception):
    pass


async def _enc_opt(svc: EncryptionService, value: str | None, user_id: int) -> str | None:
    if value is None:
        return None
    return await svc.encrypt(value, user_id)


async def _dec_opt(svc: EncryptionService, value: str | None, user_id: int) -> str | None:
    if value is None:
        return None
    return await svc.decrypt(value, user_id)


class ChronicConditionsService:
    def __init__(self, db: AsyncSession, encryption: EncryptionService):
        self._db = db
        self._encryption = encryption

    async def list_for_user(self, user_id: int) -> list[ChronicConditionResponse]:
        result = await self._db.execute(
            select(ChronicCondition)
            .where(ChronicCondition.user_id == user_id)
            .order_by(desc(ChronicCondition.created_at))
        )
        return [await self._decrypt(row) for row in result.scalars()]

    async def create(
        self, user_id: int, data: ChronicConditionCreate
    ) -> ChronicConditionResponse:
        enc = self._encryption
        row = ChronicCondition(
            user_id=user_id,
            name=await enc.encrypt(data.name, user_id),
            icd10_code=await _enc_opt(enc, data.icd10_code, user_id),
            diagnosed_at=await _enc_opt(
                enc,
                data.diagnosed_at.isoformat() if data.diagnosed_at else None,
                user_id,
            ),
            note=await _enc_opt(enc, data.note, user_id),
            is_active=data.is_active,
        )
        self._db.add(row)
        await self._db.commit()
        await self._db.refresh(row)
        log.info("profile.chronic.created", user_id=user_id, id=row.id)
        return await self._decrypt(row)

    async def update(
        self, user_id: int, condition_id: int, data: ChronicConditionUpdate
    ) -> ChronicConditionResponse:
        row = await self._get_owned(user_id, condition_id)
        enc = self._encryption
        updates = data.model_dump(exclude_unset=True)
        if "name" in updates:
            row.name = await enc.encrypt(updates["name"], user_id)
        if "icd10_code" in updates:
            row.icd10_code = await _enc_opt(enc, updates["icd10_code"], user_id)
        if "diagnosed_at" in updates:
            new_date: date | None = updates["diagnosed_at"]
            row.diagnosed_at = await _enc_opt(
                enc, new_date.isoformat() if new_date else None, user_id
            )
        if "note" in updates:
            row.note = await _enc_opt(enc, updates["note"], user_id)
        if "is_active" in updates:
            row.is_active = bool(updates["is_active"])
        await self._db.commit()
        await self._db.refresh(row)
        log.info("profile.chronic.updated", user_id=user_id, id=row.id)
        return await self._decrypt(row)

    async def delete(self, user_id: int, condition_id: int) -> None:
        row = await self._get_owned(user_id, condition_id)
        await self._db.delete(row)
        await self._db.commit()
        log.info("profile.chronic.deleted", user_id=user_id, id=condition_id)

    async def _get_owned(self, user_id: int, condition_id: int) -> ChronicCondition:
        result = await self._db.execute(
            select(ChronicCondition).where(
                ChronicCondition.id == condition_id,
                ChronicCondition.user_id == user_id,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise ChronicConditionNotFoundError()
        return row

    async def _decrypt(self, row: ChronicCondition) -> ChronicConditionResponse:
        enc = self._encryption
        uid = row.user_id
        diagnosed_str = await _dec_opt(enc, row.diagnosed_at, uid)
        return ChronicConditionResponse(
            id=row.id,
            user_id=uid,
            name=await enc.decrypt(row.name, uid),
            icd10_code=await _dec_opt(enc, row.icd10_code, uid),
            diagnosed_at=date.fromisoformat(diagnosed_str) if diagnosed_str else None,
            note=await _dec_opt(enc, row.note, uid),
            is_active=row.is_active,
            created_at=row.created_at,
        )
