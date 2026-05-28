"""Patient profile + weight-history service.

Все 🔒-поля проходят через `EncryptionService` строго в этом слое: API
получает уже расшифрованные DTO. Это поддерживает инвариант мастер-промпта
§5.1: API не работает с моделями БД напрямую.
"""

from __future__ import annotations

from datetime import date, datetime

import structlog
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.patient_profile import PatientProfile, WeightHistory
from app.schemas.profile import (
    Gender,
    PatientProfileCreate,
    PatientProfileResponse,
    PatientProfileUpdate,
    WeightRecordCreate,
    WeightRecordResponse,
)
from app.services.encryption_service import EncryptionService

log = structlog.get_logger(__name__)


# ---------- Exceptions ----------------------------------------------------- #


class ProfileError(Exception):
    """Base profile-service error."""


class ProfileNotFoundError(ProfileError):
    pass


class ProfileAlreadyExistsError(ProfileError):
    pass


# ---------- Helpers -------------------------------------------------------- #


async def _enc_opt(svc: EncryptionService, value: str | None, user_id: int) -> str | None:
    """Encrypt a nullable string — preserve `None` and empty string semantics."""
    if value is None:
        return None
    return await svc.encrypt(value, user_id)


async def _dec_opt(svc: EncryptionService, value: str | None, user_id: int) -> str | None:
    if value is None:
        return None
    return await svc.decrypt(value, user_id)


def _str_or_none(value: float | None) -> str | None:
    return None if value is None else str(value)


def _float_or_none(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _date_or_none(value: str | None) -> date | None:
    if value is None or value == "":
        return None
    return date.fromisoformat(value)


# ---------- Service -------------------------------------------------------- #


class PatientProfileService:
    def __init__(self, db: AsyncSession, encryption: EncryptionService):
        self._db = db
        self._encryption = encryption

    async def _get_profile_row(self, user_id: int) -> PatientProfile | None:
        result = await self._db.execute(
            select(PatientProfile).where(PatientProfile.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def _decrypt_profile(self, row: PatientProfile) -> PatientProfileResponse:
        enc = self._encryption
        uid = row.user_id
        return PatientProfileResponse(
            id=row.id,
            user_id=uid,
            first_name=await enc.decrypt(row.first_name, uid),
            last_name=await enc.decrypt(row.last_name, uid),
            middle_name=await _dec_opt(enc, row.middle_name, uid),
            birth_date=date.fromisoformat(await enc.decrypt(row.birth_date, uid)),
            gender=Gender(await enc.decrypt(row.gender, uid)),
            blood_type=await _dec_opt(enc, row.blood_type, uid),
            height_cm=_float_or_none(await _dec_opt(enc, row.height_cm, uid)),
            weight_kg=_float_or_none(await _dec_opt(enc, row.weight_kg, uid)),
            emergency_contact=await _dec_opt(enc, row.emergency_contact, uid),
            insurance_info=await _dec_opt(enc, row.insurance_info, uid),
            city=await _dec_opt(enc, row.city, uid),
            timezone=row.timezone,
            updated_at=row.updated_at,
        )

    async def get_profile(self, user_id: int) -> PatientProfileResponse:
        row = await self._get_profile_row(user_id)
        if row is None:
            raise ProfileNotFoundError()
        return await self._decrypt_profile(row)

    async def create_profile(
        self, user_id: int, data: PatientProfileCreate
    ) -> PatientProfileResponse:
        existing = await self._get_profile_row(user_id)
        if existing is not None:
            raise ProfileAlreadyExistsError()

        enc = self._encryption
        row = PatientProfile(
            user_id=user_id,
            first_name=await enc.encrypt(data.first_name, user_id),
            last_name=await enc.encrypt(data.last_name, user_id),
            middle_name=await _enc_opt(enc, data.middle_name, user_id),
            birth_date=await enc.encrypt(data.birth_date.isoformat(), user_id),
            gender=await enc.encrypt(data.gender.value, user_id),
            blood_type=await _enc_opt(enc, data.blood_type, user_id),
            height_cm=await _enc_opt(enc, _str_or_none(data.height_cm), user_id),
            weight_kg=await _enc_opt(enc, _str_or_none(data.weight_kg), user_id),
            emergency_contact=await _enc_opt(enc, data.emergency_contact, user_id),
            insurance_info=await _enc_opt(enc, data.insurance_info, user_id),
            city=await _enc_opt(enc, data.city, user_id),
            timezone=data.timezone,
        )
        self._db.add(row)
        await self._db.commit()
        await self._db.refresh(row)
        log.info("profile.created", user_id=user_id)
        return await self._decrypt_profile(row)

    async def update_profile(
        self, user_id: int, data: PatientProfileUpdate
    ) -> PatientProfileResponse:
        row = await self._get_profile_row(user_id)
        if row is None:
            raise ProfileNotFoundError()

        enc = self._encryption
        # Применяем только переданные поля (model_dump(exclude_unset=True)).
        updates = data.model_dump(exclude_unset=True)

        if "first_name" in updates:
            row.first_name = await enc.encrypt(updates["first_name"], user_id)
        if "last_name" in updates:
            row.last_name = await enc.encrypt(updates["last_name"], user_id)
        if "middle_name" in updates:
            row.middle_name = await _enc_opt(enc, updates["middle_name"], user_id)
        if "birth_date" in updates:
            row.birth_date = await enc.encrypt(
                updates["birth_date"].isoformat(), user_id
            )
        if "gender" in updates:
            row.gender = await enc.encrypt(updates["gender"].value, user_id)
        if "blood_type" in updates:
            row.blood_type = await _enc_opt(enc, updates["blood_type"], user_id)
        if "height_cm" in updates:
            row.height_cm = await _enc_opt(
                enc, _str_or_none(updates["height_cm"]), user_id
            )
        if "weight_kg" in updates:
            row.weight_kg = await _enc_opt(
                enc, _str_or_none(updates["weight_kg"]), user_id
            )
        if "emergency_contact" in updates:
            row.emergency_contact = await _enc_opt(
                enc, updates["emergency_contact"], user_id
            )
        if "insurance_info" in updates:
            row.insurance_info = await _enc_opt(enc, updates["insurance_info"], user_id)
        if "city" in updates:
            row.city = await _enc_opt(enc, updates["city"], user_id)
        if "timezone" in updates:
            row.timezone = updates["timezone"]

        await self._db.commit()
        await self._db.refresh(row)
        log.info("profile.updated", user_id=user_id, fields=list(updates.keys()))
        return await self._decrypt_profile(row)

    # ---- Weight history -------------------------------------------------- #

    async def add_weight_record(
        self, user_id: int, data: WeightRecordCreate
    ) -> WeightRecordResponse:
        enc = self._encryption
        row = WeightHistory(
            user_id=user_id,
            weight_kg=await enc.encrypt(str(data.weight_kg), user_id),
            note=await _enc_opt(enc, data.note, user_id),
        )
        self._db.add(row)

        # Автоматически обновляем последний вес в профиле, если он есть.
        profile = await self._get_profile_row(user_id)
        if profile is not None:
            profile.weight_kg = await enc.encrypt(str(data.weight_kg), user_id)

        await self._db.commit()
        await self._db.refresh(row)
        log.info("profile.weight_added", user_id=user_id)
        return await self._decrypt_weight(row)

    async def list_weight_history(self, user_id: int) -> list[WeightRecordResponse]:
        result = await self._db.execute(
            select(WeightHistory)
            .where(WeightHistory.user_id == user_id)
            .order_by(desc(WeightHistory.recorded_at))
        )
        return [await self._decrypt_weight(row) for row in result.scalars()]

    async def _decrypt_weight(self, row: WeightHistory) -> WeightRecordResponse:
        enc = self._encryption
        uid = row.user_id
        return WeightRecordResponse(
            id=row.id,
            user_id=uid,
            weight_kg=float(await enc.decrypt(row.weight_kg, uid)),
            note=await _dec_opt(enc, row.note, uid),
            recorded_at=row.recorded_at,
        )


__all__ = [
    "PatientProfileService",
    "ProfileAlreadyExistsError",
    "ProfileError",
    "ProfileNotFoundError",
]


# Дополнительные хелперы для тестов и других сервисов.
def _now_utc() -> datetime:  # pragma: no cover — utility
    return datetime.utcnow()
