"""Analyses service: records + values + per-parameter history.

Pattern:
  * Все 🔒-поля шифруются на запись, расшифровываются на чтение.
  * `is_abnormal` / `abnormal_type` пересчитываются автоматически на основе
    сравнения числового value с reference_min/max (см. `analysis_norm_calc`).
  * Возраст пользователя для подбора норм считается ОДИН раз на запрос (через
    расшифровку `patient_profile.birth_date`), а не на каждый value.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.analysis import AbnormalType, AnalysisRecord, AnalysisValue
from app.models.patient_profile import PatientProfile
from app.schemas.analysis import (
    AnalysisHistoryPoint,
    AnalysisHistoryResponse,
    AnalysisRecordCreate,
    AnalysisRecordFull,
    AnalysisRecordSummary,
    AnalysisRecordUpdate,
    AnalysisValueInput,
    AnalysisValueResponse,
    AnalysisValueUpdate,
)
from app.services.analysis_norms_service import AnalysisNormsService
from app.services.encryption_service import EncryptionService
from app.utils.analysis_norm_calc import calculate_abnormal, parse_number

log = structlog.get_logger(__name__)


# ---------- Exceptions ----------------------------------------------------- #


class AnalysisRecordNotFoundError(Exception):
    pass


class AnalysisValueNotFoundError(Exception):
    pass


# ---------- Helpers -------------------------------------------------------- #


async def _enc_opt(svc: EncryptionService, value: str | None, user_id: int) -> str | None:
    if value is None:
        return None
    return await svc.encrypt(value, user_id)


async def _dec_opt(svc: EncryptionService, value: str | None, user_id: int) -> str | None:
    if value is None:
        return None
    return await svc.decrypt(value, user_id)


def _age_from_birth_date(birth_date: date, today: date | None = None) -> int:
    today = today or datetime.now(UTC).date()
    years = today.year - birth_date.year
    if (today.month, today.day) < (birth_date.month, birth_date.day):
        years -= 1
    return max(years, 0)


# ---------- Service -------------------------------------------------------- #


class AnalysisService:
    def __init__(
        self,
        db: AsyncSession,
        encryption: EncryptionService,
        norms: AnalysisNormsService,
    ):
        self._db = db
        self._encryption = encryption
        self._norms = norms

    # ---- Profile helper -------------------------------------------------- #

    async def _resolve_user_demographics(self, user_id: int) -> tuple[str, int] | None:
        """Decrypt `gender` + compute `age` if the user has a profile.

        Returns `None` when the user hasn't created a profile yet — then we
        skip auto-population of reference_min/max from the dictionary.
        """
        row = (
            await self._db.execute(
                select(PatientProfile).where(PatientProfile.user_id == user_id)
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        gender = await self._encryption.decrypt(row.gender, user_id)
        try:
            birth_date = date.fromisoformat(
                await self._encryption.decrypt(row.birth_date, user_id)
            )
        except ValueError:
            return None
        return gender, _age_from_birth_date(birth_date)

    # ---- List ------------------------------------------------------------ #

    async def list_records(
        self,
        user_id: int,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        only_abnormal: bool = False,
    ) -> list[AnalysisRecordSummary]:
        stmt = (
            select(AnalysisRecord)
            .where(AnalysisRecord.user_id == user_id)
            .options(selectinload(AnalysisRecord.values))
            .order_by(AnalysisRecord.analysis_date.desc(), AnalysisRecord.id.desc())
        )
        if date_from is not None:
            stmt = stmt.where(AnalysisRecord.analysis_date >= date_from)
        if date_to is not None:
            stmt = stmt.where(AnalysisRecord.analysis_date <= date_to)

        records = (await self._db.execute(stmt)).scalars().all()
        out: list[AnalysisRecordSummary] = []
        for rec in records:
            abnormal_count = sum(1 for v in rec.values if v.is_abnormal)
            if only_abnormal and abnormal_count == 0:
                continue
            out.append(
                AnalysisRecordSummary(
                    id=rec.id,
                    user_id=rec.user_id,
                    analysis_date=rec.analysis_date,
                    lab_name=await _dec_opt(self._encryption, rec.lab_name, user_id),
                    values_count=len(rec.values),
                    abnormal_count=abnormal_count,
                )
            )
        return out

    # ---- Get ------------------------------------------------------------- #

    async def get_record(self, user_id: int, record_id: int) -> AnalysisRecordFull:
        row = await self._get_owned_record(user_id, record_id)
        return await self._decrypt_record(row)

    async def _get_owned_record(self, user_id: int, record_id: int) -> AnalysisRecord:
        stmt = (
            select(AnalysisRecord)
            .where(
                AnalysisRecord.id == record_id,
                AnalysisRecord.user_id == user_id,
            )
            .options(selectinload(AnalysisRecord.values))
        )
        row = (await self._db.execute(stmt)).scalar_one_or_none()
        if row is None:
            raise AnalysisRecordNotFoundError()
        return row

    # ---- Create ---------------------------------------------------------- #

    async def create_record(
        self, user_id: int, data: AnalysisRecordCreate
    ) -> AnalysisRecordFull:
        enc = self._encryption
        demographics = await self._resolve_user_demographics(user_id)

        record = AnalysisRecord(
            user_id=user_id,
            analysis_date=data.analysis_date,
            lab_name=await _enc_opt(enc, data.lab_name, user_id),
            doctor_referral=await _enc_opt(enc, data.doctor_referral, user_id),
            notes=await _enc_opt(enc, data.notes, user_id),
        )
        self._db.add(record)
        await self._db.flush()

        for value_input in data.values:
            await self._add_value(
                record_id=record.id,
                user_id=user_id,
                value_in=value_input,
                demographics=demographics,
            )
        await self._db.commit()
        log.info(
            "analyses.record_created",
            user_id=user_id,
            record_id=record.id,
            values=len(data.values),
        )
        return await self.get_record(user_id, record.id)

    async def _add_value(
        self,
        *,
        record_id: int,
        user_id: int,
        value_in: AnalysisValueInput,
        demographics: tuple[str, int] | None,
    ) -> AnalysisValue:
        enc = self._encryption
        # Авто-подстановка норм из справочника, если переданы не были.
        ref_min = value_in.reference_min
        ref_max = value_in.reference_max
        if (
            value_in.parameter_code
            and demographics is not None
            and (ref_min is None or ref_max is None)
        ):
            gender, age = demographics
            norm = self._norms.get_norm(value_in.parameter_code, gender=gender, age=age)
            if norm is not None:
                if ref_min is None and norm.min is not None:
                    ref_min = str(norm.min)
                if ref_max is None and norm.max is not None:
                    ref_max = str(norm.max)

        is_abnormal, abnormal_type = calculate_abnormal(
            value_in.value, ref_min, ref_max
        )

        value_row = AnalysisValue(
            record_id=record_id,
            user_id=user_id,
            parameter_code=value_in.parameter_code or _custom_code(value_in.parameter_name),
            parameter_name=await enc.encrypt(value_in.parameter_name, user_id),
            value=await enc.encrypt(value_in.value, user_id),
            unit=await enc.encrypt(value_in.unit, user_id),
            reference_min=await _enc_opt(enc, ref_min, user_id),
            reference_max=await _enc_opt(enc, ref_max, user_id),
            is_abnormal=is_abnormal,
            abnormal_type=abnormal_type,
        )
        self._db.add(value_row)
        return value_row

    # ---- Update ---------------------------------------------------------- #

    async def update_record(
        self, user_id: int, record_id: int, data: AnalysisRecordUpdate
    ) -> AnalysisRecordFull:
        record = await self._get_owned_record(user_id, record_id)
        enc = self._encryption
        updates = data.model_dump(exclude_unset=True)
        if "lab_name" in updates:
            record.lab_name = await _enc_opt(enc, updates["lab_name"], user_id)
        if "doctor_referral" in updates:
            record.doctor_referral = await _enc_opt(
                enc, updates["doctor_referral"], user_id
            )
        if "notes" in updates:
            record.notes = await _enc_opt(enc, updates["notes"], user_id)
        if "analysis_date" in updates:
            record.analysis_date = updates["analysis_date"]
        await self._db.commit()
        log.info("analyses.record_updated", user_id=user_id, record_id=record_id)
        return await self.get_record(user_id, record_id)

    async def update_value(
        self, user_id: int, value_id: int, data: AnalysisValueUpdate
    ) -> AnalysisValueResponse:
        stmt = select(AnalysisValue).where(
            AnalysisValue.id == value_id, AnalysisValue.user_id == user_id
        )
        row = (await self._db.execute(stmt)).scalar_one_or_none()
        if row is None:
            raise AnalysisValueNotFoundError()
        enc = self._encryption
        updates = data.model_dump(exclude_unset=True)
        if "value" in updates:
            row.value = await enc.encrypt(updates["value"], user_id)
        if "unit" in updates:
            row.unit = await enc.encrypt(updates["unit"], user_id)
        if "reference_min" in updates:
            row.reference_min = await _enc_opt(enc, updates["reference_min"], user_id)
        if "reference_max" in updates:
            row.reference_max = await _enc_opt(enc, updates["reference_max"], user_id)
        if "parameter_name" in updates:
            row.parameter_name = await enc.encrypt(updates["parameter_name"], user_id)

        # Пересчитываем abnormal после правки.
        value_plain = await enc.decrypt(row.value, user_id)
        ref_min_plain = await _dec_opt(enc, row.reference_min, user_id)
        ref_max_plain = await _dec_opt(enc, row.reference_max, user_id)
        row.is_abnormal, row.abnormal_type = calculate_abnormal(
            value_plain, ref_min_plain, ref_max_plain
        )
        await self._db.commit()
        log.info(
            "analyses.value_updated",
            user_id=user_id,
            value_id=value_id,
            abnormal=row.is_abnormal,
        )
        return await self._decrypt_value(row)

    # ---- Delete ---------------------------------------------------------- #

    async def delete_record(self, user_id: int, record_id: int) -> None:
        record = await self._get_owned_record(user_id, record_id)
        await self._db.delete(record)
        await self._db.commit()
        log.info("analyses.record_deleted", user_id=user_id, record_id=record_id)

    # ---- History --------------------------------------------------------- #

    async def get_parameter_history(
        self,
        user_id: int,
        parameter_code: str,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> AnalysisHistoryResponse:
        stmt = (
            select(AnalysisValue, AnalysisRecord.analysis_date)
            .join(AnalysisRecord, AnalysisRecord.id == AnalysisValue.record_id)
            .where(
                AnalysisValue.user_id == user_id,
                AnalysisValue.parameter_code == parameter_code,
            )
            .order_by(AnalysisRecord.analysis_date)
        )
        if date_from is not None:
            stmt = stmt.where(AnalysisRecord.analysis_date >= date_from)
        if date_to is not None:
            stmt = stmt.where(AnalysisRecord.analysis_date <= date_to)

        rows = (await self._db.execute(stmt)).all()
        points: list[AnalysisHistoryPoint] = []
        param_name: str | None = None
        unit: str | None = None
        enc = self._encryption
        for value_row, analysis_date in rows:
            value_plain = await enc.decrypt(value_row.value, user_id)
            unit_plain = await enc.decrypt(value_row.unit, user_id)
            ref_min = await _dec_opt(enc, value_row.reference_min, user_id)
            ref_max = await _dec_opt(enc, value_row.reference_max, user_id)
            try:
                numeric: float | None = parse_number(value_plain)
            except ValueError:
                numeric = None
            points.append(
                AnalysisHistoryPoint(
                    analysis_date=analysis_date,
                    value=value_plain,
                    value_numeric=numeric,
                    unit=unit_plain,
                    reference_min=ref_min,
                    reference_max=ref_max,
                    is_abnormal=value_row.is_abnormal,
                    abnormal_type=value_row.abnormal_type,
                )
            )
            if param_name is None:
                param_name = await enc.decrypt(value_row.parameter_name, user_id)
                unit = unit_plain
        return AnalysisHistoryResponse(
            parameter_code=parameter_code,
            parameter_name=param_name,
            unit=unit,
            points=points,
        )

    # ---- Decryption ------------------------------------------------------ #

    async def _decrypt_record(self, row: AnalysisRecord) -> AnalysisRecordFull:
        enc = self._encryption
        uid = row.user_id
        return AnalysisRecordFull(
            id=row.id,
            user_id=uid,
            analysis_date=row.analysis_date,
            lab_name=await _dec_opt(enc, row.lab_name, uid),
            doctor_referral=await _dec_opt(enc, row.doctor_referral, uid),
            notes=await _dec_opt(enc, row.notes, uid),
            created_at=row.created_at,
            values=[await self._decrypt_value(v) for v in row.values],
        )

    async def _decrypt_value(self, row: AnalysisValue) -> AnalysisValueResponse:
        enc = self._encryption
        uid = row.user_id
        return AnalysisValueResponse(
            id=row.id,
            record_id=row.record_id,
            user_id=uid,
            parameter_code=row.parameter_code,
            parameter_name=await enc.decrypt(row.parameter_name, uid),
            value=await enc.decrypt(row.value, uid),
            unit=await enc.decrypt(row.unit, uid),
            reference_min=await _dec_opt(enc, row.reference_min, uid),
            reference_max=await _dec_opt(enc, row.reference_max, uid),
            is_abnormal=row.is_abnormal,
            abnormal_type=row.abnormal_type,
        )


def _custom_code(parameter_name: str) -> str:
    """Stable per-record custom code for parameters not in the dictionary.

    Используется, когда пользователь ввёл свой параметр без выбора из
    справочника. Это позволяет группировать одинаковые названия в рамках
    одного пользователя; графики динамики работать всё равно будут, если
    пользователь использует одинаковое название.
    """
    import hashlib

    digest = hashlib.sha1(parameter_name.lower().encode("utf-8")).hexdigest()[:10]
    return f"custom_{digest}"
