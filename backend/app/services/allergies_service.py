"""Allergies CRUD service."""

from __future__ import annotations

import structlog
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.patient_profile import Allergy, AllergySeverity
from app.schemas.profile import AllergyCreate, AllergyResponse, AllergyUpdate
from app.services.encryption_service import EncryptionService

log = structlog.get_logger(__name__)


class AllergyNotFoundError(Exception):
    pass


async def _enc_opt(svc: EncryptionService, value: str | None, user_id: int) -> str | None:
    if value is None:
        return None
    return await svc.encrypt(value, user_id)


async def _dec_opt(svc: EncryptionService, value: str | None, user_id: int) -> str | None:
    if value is None:
        return None
    return await svc.decrypt(value, user_id)


class AllergiesService:
    def __init__(self, db: AsyncSession, encryption: EncryptionService):
        self._db = db
        self._encryption = encryption

    async def list_for_user(self, user_id: int) -> list[AllergyResponse]:
        result = await self._db.execute(
            select(Allergy)
            .where(Allergy.user_id == user_id)
            .order_by(desc(Allergy.created_at))
        )
        return [await self._decrypt(row) for row in result.scalars()]

    async def create(self, user_id: int, data: AllergyCreate) -> AllergyResponse:
        enc = self._encryption
        row = Allergy(
            user_id=user_id,
            allergen=await enc.encrypt(data.allergen, user_id),
            reaction=await _enc_opt(enc, data.reaction, user_id),
            note=await _enc_opt(enc, data.note, user_id),
            severity=data.severity,
        )
        self._db.add(row)
        await self._db.commit()
        await self._db.refresh(row)
        log.info("profile.allergy.created", user_id=user_id, id=row.id)
        return await self._decrypt(row)

    async def update(
        self, user_id: int, allergy_id: int, data: AllergyUpdate
    ) -> AllergyResponse:
        row = await self._get_owned(user_id, allergy_id)
        enc = self._encryption
        updates = data.model_dump(exclude_unset=True)
        if "allergen" in updates:
            row.allergen = await enc.encrypt(updates["allergen"], user_id)
        if "reaction" in updates:
            row.reaction = await _enc_opt(enc, updates["reaction"], user_id)
        if "note" in updates:
            row.note = await _enc_opt(enc, updates["note"], user_id)
        if "severity" in updates:
            row.severity = AllergySeverity(updates["severity"])
        await self._db.commit()
        await self._db.refresh(row)
        log.info("profile.allergy.updated", user_id=user_id, id=row.id)
        return await self._decrypt(row)

    async def delete(self, user_id: int, allergy_id: int) -> None:
        row = await self._get_owned(user_id, allergy_id)
        await self._db.delete(row)
        await self._db.commit()
        log.info("profile.allergy.deleted", user_id=user_id, id=allergy_id)

    async def _get_owned(self, user_id: int, allergy_id: int) -> Allergy:
        result = await self._db.execute(
            select(Allergy).where(
                Allergy.id == allergy_id,
                Allergy.user_id == user_id,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise AllergyNotFoundError()
        return row

    async def _decrypt(self, row: Allergy) -> AllergyResponse:
        enc = self._encryption
        uid = row.user_id
        return AllergyResponse(
            id=row.id,
            user_id=uid,
            allergen=await enc.decrypt(row.allergen, uid),
            reaction=await _dec_opt(enc, row.reaction, uid),
            note=await _dec_opt(enc, row.note, uid),
            severity=row.severity,
            created_at=row.created_at,
        )
