"""ExportService — генерация ZIP со всеми данными пользователя (ФЗ-152).

В архив попадают расшифрованные значения: пользователь скачивает СВОИ
данные, на момент скачивания у него есть пароль → DEK в Redis_keys.
Если DEK потерян (Redis рестартился) — возвращаем 401 session_key_lost.

Состав архива:
  ─ profile.json           ┐
  ─ chronic_conditions.json│
  ─ allergies.json         │ медданные пациента (расшифрованные)
  ─ family_history.json    │
  ─ analyses.json          ┘
  ─ ai_conversations.json  диалоги с ИИ (расшифрованные)
  ─ tickets.json           обращения в поддержку (не шифровались)
  ─ telegram_binding.json  привязка Telegram (если есть)
  ─ tickets/{id}/{file}    скриншоты тикетов
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai import AIConversation, AIMessage
from app.models.analysis import AnalysisRecord, AnalysisValue
from app.models.patient_profile import (
    Allergy,
    ChronicCondition,
    FamilyHistory,
    PatientProfile,
    WeightHistory,
)
from app.models.support import SupportTicket, TicketAttachment, TicketComment
from app.models.telegram import TelegramBinding
from app.models.user import User
from app.services.encryption_service import EncryptionService

log = structlog.get_logger(__name__)


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


class ExportService:
    def __init__(
        self,
        db: AsyncSession,
        encryption: EncryptionService,
        uploads_root: Path,
    ):
        self._db = db
        self._encryption = encryption
        self._uploads_root = uploads_root

    async def _decrypt(self, value: str | None, user_id: int) -> str | None:
        if value is None or value == "":
            return value
        return await self._encryption.decrypt(value, user_id)

    async def build_zip(self, user: User) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr(
                "README.txt",
                "Экспорт данных МедАрхив\n"
                f"Пользователь: {user.email}\n"
                f"Дата: {datetime.now(UTC).isoformat(timespec='seconds')}\n\n"
                "Все медицинские данные расшифрованы. Храните файл\n"
                "в безопасном месте — он содержит вашу личную информацию.\n",
            )

            z.writestr(
                "user.json",
                json.dumps(
                    {
                        "id": user.id,
                        "email": user.email,
                        "username": user.username,
                        "role": user.role.value,
                        "created_at": _iso(user.created_at),
                        "last_login_at": _iso(user.last_login_at),
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            )

            await self._dump_profile(z, user.id)
            await self._dump_chronic(z, user.id)
            await self._dump_allergies(z, user.id)
            await self._dump_family(z, user.id)
            await self._dump_analyses(z, user.id)
            await self._dump_ai(z, user.id)
            await self._dump_tickets(z, user.id)
            await self._dump_telegram(z, user.id)

        log.info("export.zip_built", user_id=user.id, size=buf.tell())
        return buf.getvalue()

    async def _dump_profile(self, z: zipfile.ZipFile, user_id: int) -> None:
        result = await self._db.execute(
            select(PatientProfile).where(PatientProfile.user_id == user_id)
        )
        profile = result.scalar_one_or_none()
        if profile is None:
            return
        payload: dict[str, Any] = {
            "first_name": await self._decrypt(profile.first_name, user_id),
            "last_name": await self._decrypt(profile.last_name, user_id),
            "middle_name": await self._decrypt(profile.middle_name, user_id),
            "birth_date": await self._decrypt(profile.birth_date, user_id),
            "gender": await self._decrypt(profile.gender, user_id),
            "blood_type": await self._decrypt(profile.blood_type, user_id),
            "height_cm": await self._decrypt(profile.height_cm, user_id),
            "weight_kg": await self._decrypt(profile.weight_kg, user_id),
            "emergency_contact": await self._decrypt(
                profile.emergency_contact, user_id
            ),
            "insurance_info": await self._decrypt(profile.insurance_info, user_id),
            "city": await self._decrypt(profile.city, user_id),
            "timezone": profile.timezone,
            "updated_at": _iso(profile.updated_at),
        }
        z.writestr(
            "profile.json", json.dumps(payload, ensure_ascii=False, indent=2)
        )

        weights = await self._db.execute(
            select(WeightHistory).where(WeightHistory.user_id == user_id)
        )
        weight_history = [
            {
                "weight_kg": await self._decrypt(w.weight_kg, user_id),
                "note": await self._decrypt(w.note, user_id),
                "recorded_at": _iso(w.recorded_at),
            }
            for w in weights.scalars()
        ]
        z.writestr(
            "weight_history.json",
            json.dumps(weight_history, ensure_ascii=False, indent=2),
        )

    async def _dump_chronic(self, z: zipfile.ZipFile, user_id: int) -> None:
        result = await self._db.execute(
            select(ChronicCondition).where(ChronicCondition.user_id == user_id)
        )
        items = [
            {
                "name": await self._decrypt(c.name, user_id),
                "icd10_code": await self._decrypt(c.icd10_code, user_id),
                "diagnosed_at": await self._decrypt(c.diagnosed_at, user_id),
                "note": await self._decrypt(c.note, user_id),
                "is_active": c.is_active,
            }
            for c in result.scalars()
        ]
        z.writestr(
            "chronic_conditions.json",
            json.dumps(items, ensure_ascii=False, indent=2),
        )

    async def _dump_allergies(self, z: zipfile.ZipFile, user_id: int) -> None:
        result = await self._db.execute(
            select(Allergy).where(Allergy.user_id == user_id)
        )
        items = [
            {
                "allergen": await self._decrypt(a.allergen, user_id),
                "reaction": await self._decrypt(a.reaction, user_id),
                "note": await self._decrypt(a.note, user_id),
                "severity": a.severity.value if a.severity else None,
            }
            for a in result.scalars()
        ]
        z.writestr(
            "allergies.json", json.dumps(items, ensure_ascii=False, indent=2)
        )

    async def _dump_family(self, z: zipfile.ZipFile, user_id: int) -> None:
        result = await self._db.execute(
            select(FamilyHistory).where(FamilyHistory.user_id == user_id)
        )
        items = []
        for f in result.scalars():
            items.append(
                {
                    "relation": await self._decrypt(f.relation, user_id),
                    "condition": await self._decrypt(f.condition, user_id),
                    "note": await self._decrypt(f.note, user_id),
                }
            )
        z.writestr(
            "family_history.json",
            json.dumps(items, ensure_ascii=False, indent=2),
        )

    async def _dump_analyses(self, z: zipfile.ZipFile, user_id: int) -> None:
        records = await self._db.execute(
            select(AnalysisRecord).where(AnalysisRecord.user_id == user_id)
        )
        out = []
        for r in records.scalars():
            values_result = await self._db.execute(
                select(AnalysisValue).where(AnalysisValue.record_id == r.id)
            )
            values = []
            for v in values_result.scalars():
                values.append(
                    {
                        "parameter_code": v.parameter_code,
                        "parameter_name": await self._decrypt(
                            v.parameter_name, user_id
                        ),
                        "value": await self._decrypt(v.value, user_id),
                        "unit": await self._decrypt(v.unit, user_id),
                        "ref_min": await self._decrypt(v.ref_min, user_id),
                        "ref_max": await self._decrypt(v.ref_max, user_id),
                        "abnormal_type": (
                            v.abnormal_type.value if v.abnormal_type else None
                        ),
                    }
                )
            out.append(
                {
                    "id": r.id,
                    "analysis_date": _iso(r.analysis_date),
                    "lab": await self._decrypt(r.lab, user_id),
                    "doctor": await self._decrypt(r.doctor, user_id),
                    "notes": await self._decrypt(r.notes, user_id),
                    "values": values,
                }
            )
        z.writestr(
            "analyses.json", json.dumps(out, ensure_ascii=False, indent=2)
        )

    async def _dump_ai(self, z: zipfile.ZipFile, user_id: int) -> None:
        convs = await self._db.execute(
            select(AIConversation).where(AIConversation.user_id == user_id)
        )
        out = []
        for c in convs.scalars():
            messages_result = await self._db.execute(
                select(AIMessage)
                .where(AIMessage.conversation_id == c.id)
                .order_by(AIMessage.id)
            )
            messages = []
            for m in messages_result.scalars():
                messages.append(
                    {
                        "role": m.role.value,
                        "content": await self._decrypt(m.content, user_id),
                        "attached_data": await self._decrypt(
                            m.attached_data, user_id
                        ),
                        "created_at": _iso(m.created_at),
                    }
                )
            out.append(
                {
                    "id": c.id,
                    "title": await self._decrypt(c.title, user_id),
                    "created_at": _iso(c.created_at),
                    "messages": messages,
                }
            )
        z.writestr(
            "ai_conversations.json",
            json.dumps(out, ensure_ascii=False, indent=2),
        )

    async def _dump_tickets(self, z: zipfile.ZipFile, user_id: int) -> None:
        tickets = await self._db.execute(
            select(SupportTicket).where(SupportTicket.user_id == user_id)
        )
        out = []
        for t in tickets.scalars():
            comments_result = await self._db.execute(
                select(TicketComment).where(TicketComment.ticket_id == t.id)
            )
            comments = [
                {
                    "author_user_id": c.author_user_id,
                    "body": c.body,
                    "is_internal": c.is_internal,
                    "created_at": _iso(c.created_at),
                }
                for c in comments_result.scalars()
            ]
            attachments_result = await self._db.execute(
                select(TicketAttachment).where(TicketAttachment.ticket_id == t.id)
            )
            attachments = []
            for a in attachments_result.scalars():
                attachments.append(
                    {
                        "original_filename": a.original_filename,
                        "mime_type": a.mime_type,
                        "size_bytes": a.size_bytes,
                    }
                )
                src = self._uploads_root / "tickets" / str(t.id) / a.filename
                if src.exists():
                    z.write(
                        src,
                        arcname=f"tickets/{t.id}/{a.original_filename}",
                    )
            out.append(
                {
                    "id": t.id,
                    "type": t.type,
                    "title": t.title,
                    "description": t.description,
                    "status": t.status,
                    "created_at": _iso(t.created_at),
                    "comments": comments,
                    "attachments": attachments,
                }
            )
        z.writestr(
            "tickets.json", json.dumps(out, ensure_ascii=False, indent=2)
        )

    async def _dump_telegram(self, z: zipfile.ZipFile, user_id: int) -> None:
        binding = await self._db.execute(
            select(TelegramBinding).where(TelegramBinding.user_id == user_id)
        )
        b = binding.scalar_one_or_none()
        if b is None:
            return
        z.writestr(
            "telegram_binding.json",
            json.dumps(
                {
                    "telegram_user_id": b.telegram_user_id,
                    "telegram_username": b.telegram_username,
                    "bound_at": _iso(b.bound_at),
                    "notifications_enabled": b.notifications_enabled,
                },
                ensure_ascii=False,
                indent=2,
            ),
        )
