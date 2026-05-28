"""Family-history CRUD service."""

from __future__ import annotations

import structlog
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.patient_profile import FamilyHistory
from app.schemas.profile import (
    FamilyHistoryCreate,
    FamilyHistoryResponse,
    FamilyHistoryUpdate,
)
from app.services.encryption_service import EncryptionService

log = structlog.get_logger(__name__)


class FamilyHistoryNotFoundError(Exception):
    pass


async def _enc_opt(svc: EncryptionService, value: str | None, user_id: int) -> str | None:
    if value is None:
        return None
    return await svc.encrypt(value, user_id)


async def _dec_opt(svc: EncryptionService, value: str | None, user_id: int) -> str | None:
    if value is None:
        return None
    return await svc.decrypt(value, user_id)


class FamilyHistoryService:
    def __init__(self, db: AsyncSession, encryption: EncryptionService):
        self._db = db
        self._encryption = encryption

    async def list_for_user(self, user_id: int) -> list[FamilyHistoryResponse]:
        result = await self._db.execute(
            select(FamilyHistory)
            .where(FamilyHistory.user_id == user_id)
            .order_by(desc(FamilyHistory.created_at))
        )
        return [await self._decrypt(row) for row in result.scalars()]

    async def create(
        self, user_id: int, data: FamilyHistoryCreate
    ) -> FamilyHistoryResponse:
        enc = self._encryption
        row = FamilyHistory(
            user_id=user_id,
            relation=await enc.encrypt(data.relation, user_id),
            condition=await enc.encrypt(data.condition, user_id),
            note=await _enc_opt(enc, data.note, user_id),
        )
        self._db.add(row)
        await self._db.commit()
        await self._db.refresh(row)
        log.info("profile.family.created", user_id=user_id, id=row.id)
        return await self._decrypt(row)

    async def update(
        self, user_id: int, record_id: int, data: FamilyHistoryUpdate
    ) -> FamilyHistoryResponse:
        row = await self._get_owned(user_id, record_id)
        enc = self._encryption
        updates = data.model_dump(exclude_unset=True)
        if "relation" in updates:
            row.relation = await enc.encrypt(updates["relation"], user_id)
        if "condition" in updates:
            row.condition = await enc.encrypt(updates["condition"], user_id)
        if "note" in updates:
            row.note = await _enc_opt(enc, updates["note"], user_id)
        await self._db.commit()
        await self._db.refresh(row)
        log.info("profile.family.updated", user_id=user_id, id=row.id)
        return await self._decrypt(row)

    async def delete(self, user_id: int, record_id: int) -> None:
        row = await self._get_owned(user_id, record_id)
        await self._db.delete(row)
        await self._db.commit()
        log.info("profile.family.deleted", user_id=user_id, id=record_id)

    async def _get_owned(self, user_id: int, record_id: int) -> FamilyHistory:
        result = await self._db.execute(
            select(FamilyHistory).where(
                FamilyHistory.id == record_id,
                FamilyHistory.user_id == user_id,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise FamilyHistoryNotFoundError()
        return row

    async def _decrypt(self, row: FamilyHistory) -> FamilyHistoryResponse:
        enc = self._encryption
        uid = row.user_id
        return FamilyHistoryResponse(
            id=row.id,
            user_id=uid,
            relation=await enc.decrypt(row.relation, uid),
            condition=await enc.decrypt(row.condition, uid),
            note=await _dec_opt(enc, row.note, uid),
            created_at=row.created_at,
        )
