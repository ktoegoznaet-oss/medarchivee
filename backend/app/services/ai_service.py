"""AI assistant («Иван Иваныч») service layer.

Реализует §8 ТЗ v1.1 для этапа 5:
  * настройки пользователя (тон, сложность, провайдер),
  * беседы и сообщения с шифрованием контента и attached_data,
  * safety-проверка (suicide / medical emergency) ДО запроса в провайдер,
  * формирование системного промпта (тон + сложность + manual-режим).

Шифрование идёт строго в этом слое — API ниже получает уже расшифрованные
DTO (см. инвариант мастер-промпта §5.1).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import structlog
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import Settings
from app.models.ai import (
    AIComplexity,
    AIConversation,
    AIDataAccessMode,
    AIMessage,
    AIMessageRole,
    AIProvider,
    AISettings,
    AITone,
)
from app.models.analysis import AnalysisRecord
from app.models.patient_profile import PatientProfile
from app.schemas.ai import (
    AIConversationFull,
    AIConversationSummary,
    AIMessageDTO,
    AIMessageSendResponse,
    AISettingsResponse,
    AISettingsUpdate,
    AttachedAnalysisDTO,
    AttachedDataDTO,
    AttachedProfileDTO,
)
from app.services.ai_providers import (
    AIContentBlockedError,
    AIProviderError,
    AIServiceUnavailableError,
    RateLimitError,
)
from app.services.ai_providers.base import AIMessage as ProviderMessage
from app.services.ai_providers.factory import AIProviderFactory
from app.services.ai_safety import (
    MEDICAL_EMERGENCY_RESPONSE_TEMPLATE,
    SUICIDE_RESPONSE_TEMPLATE,
    check_medical_emergency,
    check_suicide_risk,
)
from app.services.encryption_service import EncryptionService

log = structlog.get_logger(__name__)


# ---------- Exceptions ----------------------------------------------------- #


class AIConversationNotFoundError(Exception):
    pass


class AIProviderUnavailableError(Exception):
    """User-facing wrapper around provider errors."""

    def __init__(self, message: str, *, retry_after: bool = False) -> None:
        super().__init__(message)
        self.message = message
        self.retry_after = retry_after


# ---------- Constants ----------------------------------------------------- #

_TONE_INSTRUCTIONS: dict[AITone, str] = {
    AITone.CLOSE_PERSON: (
        "Обращайся к пользователю тепло, заботливо, на «ты», как близкий человек. "
        "Например: «Привет, дорогой!». Используй ласковые обращения, но не "
        "переусердствуй."
    ),
    AITone.GOOD_FRIEND: (
        "Дружелюбно и поддерживающе, на «ты», как хороший друг. Без излишнего "
        "официоза, но и без панибратства."
    ),
    AITone.FUNNY_COLLEAGUE: (
        "С лёгким юмором, как весёлый коллега, на «ты». Уместные эмодзи "
        "допустимы (но не более 1–2 на ответ)."
    ),
    AITone.PROFESSIONAL: (
        "Профессионально, вежливо, на «Вы». Без эмодзи и сленга."
    ),
    AITone.ENCYCLOPEDIA: (
        "Сухо, по делу, без эмоций и эмодзи. Только факты. Стиль "
        "энциклопедической статьи."
    ),
}

_COMPLEXITY_INSTRUCTIONS: dict[AIComplexity, str] = {
    AIComplexity.CHILD: (
        "Объясняй максимально простыми словами, через бытовые аналогии. "
        "Минимум терминов. Как если бы рассказывал ребёнку 10 лет."
    ),
    AIComplexity.FAMILY_DOCTOR: (
        "Понятный язык, базовые медицинские термины с пояснением в скобках. "
        "Уровень — семейный врач объясняет пациенту."
    ),
    AIComplexity.PROFESSOR: (
        "Полные медицинские термины, патофизиология, при необходимости — "
        "ссылки на клинические рекомендации. Профессорский уровень."
    ),
    AIComplexity.DRY_FACTS: (
        "Только цифры, нормы, отклонения. Без объяснений, без эмоций, "
        "без «воды»."
    ),
}

_HISTORY_WINDOW = 20

_SYSTEM_PROMPT_HEAD = (
    "Ты — Иван Иваныч, виртуальный медицинский помощник в приложении "
    "«МедАрхив». Ты — мужчина. Всегда говори о себе в мужском роде: "
    "«я понял», «я помогу», «я подумал». Никогда не используй женский род.\n"
    "\n"
    "# Кто ты\n"
    "Дружелюбный и поддерживающий помощник. Объясняешь медицинские "
    "термины простыми словами. НИКОГДА не ставишь диагнозы и не "
    "назначаешь лечение. ВСЕГДА напоминаешь обращаться к врачу при "
    "серьёзных симптомах.\n"
)

_SYSTEM_PROMPT_TOPICS = (
    "\n# Темы\n"
    "Ты обсуждаешь ТОЛЬКО: здоровье, медицину, симптомы, анализы, "
    "препараты, профилактику, работу с приложением «МедАрхив». Если "
    "пользователь спрашивает что-то вне этого — вежливо откажись и "
    "переведи разговор на медицинскую тему.\n"
)

_SYSTEM_PROMPT_DONTS = (
    "\n# Что ты НЕ делаешь\n"
    "- Не ставишь диагнозы\n"
    "- Не назначаешь лечение\n"
    "- Не даёшь рекомендации по дозировке препаратов\n"
    "- Не отвечаешь на вопросы вне медицинской темы\n"
)

_SYSTEM_PROMPT_STYLE = (
    "\n# Стиль ответа\n"
    "- Краткий, по делу\n"
    "- Используй markdown для структуры (списки, выделения)\n"
    "- В конце ответа при необходимости — рекомендация обратиться к "
    "врачу\n"
)


# ---------- Service ------------------------------------------------------- #


class AIService:
    def __init__(
        self,
        db: AsyncSession,
        encryption: EncryptionService,
        provider_factory: AIProviderFactory,
        config: Settings,
    ) -> None:
        self._db = db
        self._encryption = encryption
        self._provider_factory = provider_factory
        self._config = config

    # ---- Settings -------------------------------------------------------- #

    async def get_settings(self, user_id: int) -> AISettingsResponse:
        row = await self._get_or_create_settings(user_id)
        return AISettingsResponse.model_validate(row)

    async def update_settings(
        self, user_id: int, data: AISettingsUpdate
    ) -> AISettingsResponse:
        row = await self._get_or_create_settings(user_id)
        updates = data.model_dump(exclude_unset=True)
        for field, value in updates.items():
            setattr(row, field, value)
        await self._db.commit()
        await self._db.refresh(row)
        log.info("ai.settings_updated", user_id=user_id, fields=list(updates.keys()))
        return AISettingsResponse.model_validate(row)

    async def _get_or_create_settings(self, user_id: int) -> AISettings:
        row = (
            await self._db.execute(
                select(AISettings).where(AISettings.user_id == user_id)
            )
        ).scalar_one_or_none()
        if row is not None:
            return row
        row = AISettings(user_id=user_id)
        self._db.add(row)
        await self._db.commit()
        await self._db.refresh(row)
        return row

    # ---- Conversations --------------------------------------------------- #

    async def list_conversations(
        self, user_id: int, *, include_archived: bool = False
    ) -> list[AIConversationSummary]:
        # Заранее загружаем последнее сообщение каждой беседы одним запросом.
        # Без этого был N+1 (по запросу на каждую беседу — см. C-3 в diag).
        from sqlalchemy import func

        stmt = (
            select(AIConversation)
            .where(AIConversation.user_id == user_id)
            .order_by(desc(AIConversation.updated_at))
        )
        if not include_archived:
            stmt = stmt.where(AIConversation.is_archived.is_(False))
        rows = (await self._db.execute(stmt)).scalars().all()
        if not rows:
            return []

        conv_ids = [row.id for row in rows]
        # Подзапрос: max(id) по каждой беседе → берём «последнее» сообщение.
        # Используем id вместо created_at, чтобы избежать неоднозначности при
        # одинаковых timestamp (SQLite даёт грубую секундную точность).
        latest_id_subq = (
            select(
                AIMessage.conversation_id.label("conv_id"),
                func.max(AIMessage.id).label("max_id"),
            )
            .where(
                AIMessage.user_id == user_id,
                AIMessage.conversation_id.in_(conv_ids),
            )
            .group_by(AIMessage.conversation_id)
            .subquery()
        )
        latest_stmt = (
            select(AIMessage)
            .join(latest_id_subq, AIMessage.id == latest_id_subq.c.max_id)
        )
        latest_msgs = (await self._db.execute(latest_stmt)).scalars().all()
        latest_by_conv: dict[int, AIMessage] = {
            m.conversation_id: m for m in latest_msgs
        }

        out: list[AIConversationSummary] = []
        for row in rows:
            title_plain = (
                await self._encryption.decrypt(row.title, user_id)
                if row.title
                else ""
            )
            last_msg = latest_by_conv.get(row.id)
            preview: str | None = None
            if last_msg is not None:
                decrypted = await self._encryption.decrypt(
                    last_msg.content, user_id
                )
                preview = decrypted[:100]
            out.append(
                AIConversationSummary(
                    id=row.id,
                    title=title_plain,
                    is_archived=row.is_archived,
                    created_at=row.created_at,
                    updated_at=row.updated_at,
                    last_message_preview=preview,
                )
            )
        return out

    async def create_conversation(self, user_id: int) -> AIConversationFull:
        conv = AIConversation(
            user_id=user_id,
            title=await self._encryption.encrypt("", user_id),
        )
        self._db.add(conv)
        await self._db.commit()
        await self._db.refresh(conv)
        log.info("ai.conversation_created", user_id=user_id, conversation_id=conv.id)
        return await self._conversation_to_dto(conv, user_id)

    async def archive_conversation(self, user_id: int, conversation_id: int) -> None:
        conv = await self._get_owned_conversation(user_id, conversation_id)
        conv.is_archived = True
        await self._db.commit()
        log.info(
            "ai.conversation_archived",
            user_id=user_id,
            conversation_id=conversation_id,
        )

    async def delete_conversation(self, user_id: int, conversation_id: int) -> None:
        conv = await self._get_owned_conversation(user_id, conversation_id)
        await self._db.delete(conv)
        await self._db.commit()
        log.info(
            "ai.conversation_deleted",
            user_id=user_id,
            conversation_id=conversation_id,
        )

    # ---- Messages -------------------------------------------------------- #

    async def get_conversation_messages(
        self, user_id: int, conversation_id: int
    ) -> list[AIMessageDTO]:
        await self._get_owned_conversation(user_id, conversation_id)
        stmt = (
            select(AIMessage)
            .where(
                AIMessage.conversation_id == conversation_id,
                AIMessage.user_id == user_id,
            )
            .order_by(AIMessage.id)
        )
        rows = (await self._db.execute(stmt)).scalars().all()
        return [await self._message_to_dto(row, user_id) for row in rows]

    async def send_message(
        self,
        *,
        user_id: int,
        conversation_id: int,
        user_message: str,
        attached_data: AttachedDataDTO | None,
        override_tone: AITone | None,
        override_complexity: AIComplexity | None,
    ) -> AIMessageSendResponse:
        conv = await self._get_owned_conversation(user_id, conversation_id)
        settings_row = await self._get_or_create_settings(user_id)

        snapshot = await self._build_attached_snapshot(user_id, attached_data)
        attached_payload = (
            json.dumps(snapshot, ensure_ascii=False) if snapshot else None
        )
        encrypted_user_content = await self._encryption.encrypt(
            user_message, user_id
        )
        encrypted_attached: str | None = (
            await self._encryption.encrypt(attached_payload, user_id)
            if attached_payload
            else None
        )

        # --- Safety-проверка ДО запроса в провайдер ---
        safety_event: str | None = None
        canned_response: str | None = None
        if check_suicide_risk(user_message):
            safety_event = "suicide_risk"
            canned_response = SUICIDE_RESPONSE_TEMPLATE
        elif check_medical_emergency(user_message):
            safety_event = "medical_emergency"
            canned_response = MEDICAL_EMERGENCY_RESPONSE_TEMPLATE

        if safety_event and canned_response:
            user_msg = self._add_message(
                conv_id=conv.id,
                user_id=user_id,
                role=AIMessageRole.USER,
                encrypted_content=encrypted_user_content,
                encrypted_attached=encrypted_attached,
            )
            assistant_msg = self._add_message(
                conv_id=conv.id,
                user_id=user_id,
                role=AIMessageRole.ASSISTANT,
                encrypted_content=await self._encryption.encrypt(
                    canned_response, user_id
                ),
                safety_event_type=safety_event,
            )
            # Метаданные — БЕЗ содержимого. Только тип события и id.
            log.warning(
                "ai.safety_event",
                user_id=user_id,
                conversation_id=conv.id,
                event_type=safety_event,
            )
            await self._maybe_set_title(conv, user_message, user_id)
            await self._db.commit()
            await self._db.refresh(user_msg)
            await self._db.refresh(assistant_msg)
            return AIMessageSendResponse(
                conversation=await self._conversation_to_dto(conv, user_id),
                user_message=await self._message_to_dto(user_msg, user_id),
                assistant_message=await self._message_to_dto(assistant_msg, user_id),
            )

        # --- Обычный путь: запрос в провайдер ---
        effective_tone = override_tone or settings_row.tone
        effective_complexity = override_complexity or settings_row.complexity_level

        system_prompt = self._build_system_prompt(
            tone=effective_tone,
            complexity=effective_complexity,
            data_access_mode=settings_row.data_access_mode,
            attached_snapshot=snapshot,
        )

        history = await self._load_provider_history(
            conversation_id=conv.id, user_id=user_id
        )
        history.append(ProviderMessage(role="user", content=user_message))

        provider = self._provider_factory.get(settings_row.preferred_provider)
        try:
            ai_response = await provider.generate(
                system_prompt=system_prompt,
                messages=history,
                max_tokens=self._config.gemini_max_output_tokens,
            )
        except RateLimitError as exc:
            raise AIProviderUnavailableError(str(exc), retry_after=True) from exc
        except AIContentBlockedError as exc:
            raise AIProviderUnavailableError(
                f"Запрос отклонён фильтром безопасности: {exc.reason}"
            ) from exc
        except AIServiceUnavailableError as exc:
            raise AIProviderUnavailableError(
                "ИИ-помощник временно недоступен. Попробуйте позже."
            ) from exc
        except AIProviderError as exc:
            raise AIProviderUnavailableError(str(exc)) from exc

        user_msg = self._add_message(
            conv_id=conv.id,
            user_id=user_id,
            role=AIMessageRole.USER,
            encrypted_content=encrypted_user_content,
            encrypted_attached=encrypted_attached,
        )
        assistant_msg = self._add_message(
            conv_id=conv.id,
            user_id=user_id,
            role=AIMessageRole.ASSISTANT,
            encrypted_content=await self._encryption.encrypt(
                ai_response.content, user_id
            ),
            provider=ai_response.provider,
            model=ai_response.model,
            tokens_used=ai_response.tokens_used,
        )
        await self._maybe_set_title(conv, user_message, user_id)
        await self._db.commit()
        await self._db.refresh(user_msg)
        await self._db.refresh(assistant_msg)

        log.info(
            "ai.message_sent",
            user_id=user_id,
            conversation_id=conv.id,
            tokens=ai_response.tokens_used,
            provider=ai_response.provider,
        )

        return AIMessageSendResponse(
            conversation=await self._conversation_to_dto(conv, user_id),
            user_message=await self._message_to_dto(user_msg, user_id),
            assistant_message=await self._message_to_dto(assistant_msg, user_id),
        )

    # ---- Internals ------------------------------------------------------- #

    def _add_message(
        self,
        *,
        conv_id: int,
        user_id: int,
        role: AIMessageRole,
        encrypted_content: str,
        encrypted_attached: str | None = None,
        safety_event_type: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        tokens_used: int | None = None,
    ) -> AIMessage:
        msg = AIMessage(
            conversation_id=conv_id,
            user_id=user_id,
            role=role,
            content=encrypted_content,
            attached_data=encrypted_attached,
            safety_event_type=safety_event_type,
            provider=provider,
            model=model,
            tokens_used=tokens_used,
        )
        self._db.add(msg)
        return msg

    async def _get_owned_conversation(
        self, user_id: int, conversation_id: int
    ) -> AIConversation:
        row = (
            await self._db.execute(
                select(AIConversation).where(
                    AIConversation.id == conversation_id,
                    AIConversation.user_id == user_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise AIConversationNotFoundError()
        return row

    async def _maybe_set_title(
        self, conv: AIConversation, user_message: str, user_id: int
    ) -> None:
        """Set conversation title from the first user message (50 chars).

        Title remains encrypted at rest; on stage 5 we don't run a separate
        AI-summarisation pass — first message excerpt is a good-enough hint.
        """
        existing_plain = (
            await self._encryption.decrypt(conv.title, user_id) if conv.title else ""
        )
        if existing_plain:
            return
        trimmed = user_message.strip().splitlines()[0][:50] if user_message else ""
        if not trimmed:
            return
        conv.title = await self._encryption.encrypt(trimmed, user_id)

    async def _latest_message_preview(
        self, conversation_id: int, user_id: int
    ) -> str | None:
        row = (
            await self._db.execute(
                select(AIMessage)
                .where(
                    AIMessage.conversation_id == conversation_id,
                    AIMessage.user_id == user_id,
                )
                .order_by(desc(AIMessage.id))
                .limit(1)
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        decrypted = await self._encryption.decrypt(row.content, user_id)
        return decrypted[:100]

    async def _load_provider_history(
        self, *, conversation_id: int, user_id: int
    ) -> list[ProviderMessage]:
        stmt = (
            select(AIMessage)
            .where(
                AIMessage.conversation_id == conversation_id,
                AIMessage.user_id == user_id,
                AIMessage.safety_event_type.is_(None),
            )
            .order_by(desc(AIMessage.id))
            .limit(_HISTORY_WINDOW)
        )
        rows = (await self._db.execute(stmt)).scalars().all()
        history: list[ProviderMessage] = []
        # Stored newest-first; we want oldest-first for the provider.
        for row in reversed(list(rows)):
            content_plain = await self._encryption.decrypt(row.content, user_id)
            history.append(
                ProviderMessage(role=row.role.value, content=content_plain)
            )
        return history

    async def _conversation_to_dto(
        self, conv: AIConversation, user_id: int
    ) -> AIConversationFull:
        title_plain = (
            await self._encryption.decrypt(conv.title, user_id) if conv.title else ""
        )
        return AIConversationFull(
            id=conv.id,
            title=title_plain,
            is_archived=conv.is_archived,
            created_at=conv.created_at,
            updated_at=conv.updated_at,
        )

    async def _message_to_dto(
        self, msg: AIMessage, user_id: int
    ) -> AIMessageDTO:
        content_plain = await self._encryption.decrypt(msg.content, user_id)
        attached: AttachedDataDTO | None = None
        if msg.attached_data:
            try:
                payload = json.loads(
                    await self._encryption.decrypt(msg.attached_data, user_id)
                )
                attached = self._snapshot_to_dto(payload)
            except (json.JSONDecodeError, ValueError):
                attached = None
        return AIMessageDTO(
            id=msg.id,
            conversation_id=msg.conversation_id,
            role=msg.role,
            content=content_plain,
            attached_data=attached,
            safety_event_type=msg.safety_event_type,
            provider=msg.provider,
            model=msg.model,
            tokens_used=msg.tokens_used,
            created_at=msg.created_at,
        )

    @staticmethod
    def _snapshot_to_dto(payload: object) -> AttachedDataDTO | None:
        """Decode the persisted snapshot back into a slim DTO for UI.

        We don't store every detail in the message — the UI uses this only
        to render the «прикреплено: профиль + 3 анализа» chip in history.
        """
        if not isinstance(payload, dict):
            return None
        analyses = payload.get("analyses")
        analysis_ids: list[int] = []
        if isinstance(analyses, list):
            for item in analyses:
                if isinstance(item, dict) and isinstance(item.get("id"), int):
                    analysis_ids.append(item["id"])
        include_profile = bool(payload.get("profile"))
        if not include_profile and not analysis_ids:
            return None
        return AttachedDataDTO(
            include_profile=include_profile, analysis_ids=analysis_ids
        )

    # ---- Attached-data snapshot ----------------------------------------- #

    async def _build_attached_snapshot(
        self, user_id: int, requested: AttachedDataDTO | None
    ) -> dict[str, object] | None:
        if requested is None or (
            not requested.include_profile and not requested.analysis_ids
        ):
            return None

        snapshot: dict[str, object] = {}
        if requested.include_profile:
            profile = await self._load_profile_snapshot(user_id)
            if profile is not None:
                snapshot["profile"] = profile.model_dump()
        if requested.analysis_ids:
            analyses = await self._load_analysis_snapshots(
                user_id, requested.analysis_ids
            )
            if analyses:
                snapshot["analyses"] = [a.model_dump() for a in analyses]
        return snapshot or None

    async def _load_profile_snapshot(
        self, user_id: int
    ) -> AttachedProfileDTO | None:
        row = (
            await self._db.execute(
                select(PatientProfile).where(PatientProfile.user_id == user_id)
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        enc = self._encryption
        return AttachedProfileDTO(
            first_name=await enc.decrypt(row.first_name, user_id),
            last_name=await enc.decrypt(row.last_name, user_id),
            birth_date=await enc.decrypt(row.birth_date, user_id),
            gender=await enc.decrypt(row.gender, user_id),
            height_cm=await _dec_opt(enc, row.height_cm, user_id),
            weight_kg=await _dec_opt(enc, row.weight_kg, user_id),
            blood_type=await _dec_opt(enc, row.blood_type, user_id),
            city=await _dec_opt(enc, row.city, user_id),
        )

    async def _load_analysis_snapshots(
        self, user_id: int, analysis_ids: list[int]
    ) -> list[AttachedAnalysisDTO]:
        stmt = (
            select(AnalysisRecord)
            .where(
                AnalysisRecord.user_id == user_id,
                AnalysisRecord.id.in_(analysis_ids),
            )
            .options(selectinload(AnalysisRecord.values))
            .order_by(desc(AnalysisRecord.analysis_date))
        )
        rows = (await self._db.execute(stmt)).scalars().all()
        enc = self._encryption
        out: list[AttachedAnalysisDTO] = []
        for record in rows:
            values_payload: list[dict[str, object]] = []
            for v in record.values:
                values_payload.append(
                    {
                        "parameter_code": v.parameter_code,
                        "parameter_name": await enc.decrypt(
                            v.parameter_name, user_id
                        ),
                        "value": await enc.decrypt(v.value, user_id),
                        "unit": await enc.decrypt(v.unit, user_id),
                        "reference_min": await _dec_opt(
                            enc, v.reference_min, user_id
                        ),
                        "reference_max": await _dec_opt(
                            enc, v.reference_max, user_id
                        ),
                        "is_abnormal": v.is_abnormal,
                        "abnormal_type": v.abnormal_type.value,
                    }
                )
            out.append(
                AttachedAnalysisDTO(
                    id=record.id,
                    analysis_date=record.analysis_date.isoformat(),
                    lab_name=await _dec_opt(enc, record.lab_name, user_id),
                    values=values_payload,
                )
            )
        return out

    # ---- System prompt -------------------------------------------------- #

    def _build_system_prompt(
        self,
        *,
        tone: AITone,
        complexity: AIComplexity,
        data_access_mode: AIDataAccessMode,
        attached_snapshot: dict[str, object] | None,
    ) -> str:
        parts: list[str] = [_SYSTEM_PROMPT_HEAD]

        parts.append(f"\n# Тон общения\n{_TONE_INSTRUCTIONS[tone]}\n")
        parts.append(
            f"\n# Уровень сложности\n{_COMPLEXITY_INSTRUCTIONS[complexity]}\n"
        )

        parts.append(_SYSTEM_PROMPT_TOPICS)

        # Data-access section
        mode_label = (
            "«Ручной»"
            if data_access_mode == AIDataAccessMode.MANUAL
            else "«Полный»"
        )
        parts.append(f"\n# Доступ к данным пользователя\nРежим: {mode_label}.\n")
        if attached_snapshot:
            payload = json.dumps(attached_snapshot, ensure_ascii=False, indent=2)
            parts.append(
                "В этом сообщении пользователь явно прикрепил следующие "
                f"данные:\n```json\n{payload}\n```\n"
                "Используй их в ответе. Не выдумывай данных, которых в "
                "снапшоте нет.\n"
            )
        else:
            parts.append(
                "У тебя нет автоматического доступа к данным пользователя. "
                "Если для ответа нужна медицинская информация о нём — "
                "попроси явно прикрепить её через интерфейс (кнопка "
                "«Прикрепить данные»).\n"
            )

        parts.append(_SYSTEM_PROMPT_DONTS)
        parts.append(_SYSTEM_PROMPT_STYLE)

        # Timestamp context — иногда полезно: ИИ узнаёт «сегодняшнюю» дату.
        today = datetime.now(UTC).date().isoformat()
        parts.append(f"\n# Контекст\nСегодня: {today}.\n")

        return "".join(parts)


async def _dec_opt(
    svc: EncryptionService, value: str | None, user_id: int
) -> str | None:
    if value is None:
        return None
    return await svc.decrypt(value, user_id)


# Public surface used by the API layer and tests.
__all__ = [
    "AIComplexity",
    "AIConversationNotFoundError",
    "AIDataAccessMode",
    "AIProvider",
    "AIProviderUnavailableError",
    "AIService",
    "AITone",
]
