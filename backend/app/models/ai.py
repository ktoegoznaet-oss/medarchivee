"""AI assistant («Иван Иваныч») ORM models.

Tables follow ТЗ v1.1 §5.12. На этапе 5 покрыт только базовый чат:
  * `ai_settings`       — per-user preferences (tone, complexity, provider).
  * `ai_conversations`  — conversation threads.
  * `ai_messages`       — encrypted user/assistant messages.

Шифруются (🔒) — поля свободного текста с медицинским содержанием:
  * `ai_messages.content`        — текст сообщения.
  * `ai_messages.attached_data`  — JSON-снапшот данных, переданных ИИ.
  * `ai_settings.openai_api_key` / `claude_api_key` — на будущее (v1.1).

Поля `complexity_level`/`tone`/`data_access_mode`/`preferred_provider`
не шифруются: enum-значения и сами по себе не раскрывают медицинских
данных пользователя; их фильтрация в SQL нужна для UI.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class AIProvider(str, Enum):
    GEMINI = "gemini"
    # OPENAI, CLAUDE — для будущих версий (v1.1+).


class AIComplexity(str, Enum):
    CHILD = "child"
    FAMILY_DOCTOR = "family_doctor"
    PROFESSOR = "professor"
    DRY_FACTS = "dry_facts"


class AITone(str, Enum):
    CLOSE_PERSON = "close_person"
    GOOD_FRIEND = "good_friend"
    FUNNY_COLLEAGUE = "funny_colleague"
    PROFESSIONAL = "professional"
    ENCYCLOPEDIA = "encyclopedia"


class AIDataAccessMode(str, Enum):
    MANUAL = "manual"
    FULL = "full"  # активируется на этапе 12


class AIMessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"


class AISettings(Base):
    __tablename__ = "ai_settings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    preferred_provider: Mapped[AIProvider] = mapped_column(
        SqlEnum(AIProvider, native_enum=False, length=20),
        default=AIProvider.GEMINI,
        nullable=False,
    )
    # 🔒 — на этапе 5 не используются, заполняются в v1.1.
    openai_api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    claude_api_key: Mapped[str | None] = mapped_column(Text, nullable=True)

    complexity_level: Mapped[AIComplexity] = mapped_column(
        SqlEnum(AIComplexity, native_enum=False, length=20),
        default=AIComplexity.FAMILY_DOCTOR,
        nullable=False,
    )
    tone: Mapped[AITone] = mapped_column(
        SqlEnum(AITone, native_enum=False, length=20),
        default=AITone.GOOD_FRIEND,
        nullable=False,
    )
    data_access_mode: Mapped[AIDataAccessMode] = mapped_column(
        SqlEnum(AIDataAccessMode, native_enum=False, length=20),
        default=AIDataAccessMode.MANUAL,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class AIConversation(Base):
    __tablename__ = "ai_conversations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Заголовок — короткий, генерится из первого сообщения (первые 50 символов).
    # Сами 50 символов могут содержать чувствительные данные, поэтому шифруем.
    # 🔒
    title: Mapped[str] = mapped_column(Text, nullable=False, default="")

    is_archived: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    messages: Mapped[list["AIMessage"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        order_by="AIMessage.id",
    )

    __table_args__ = (
        Index("ix_ai_conversations_user_updated", "user_id", "updated_at"),
    )


class AIMessage(Base):
    __tablename__ = "ai_messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("ai_conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Дублируем user_id для дешёвой проверки изоляции (см. analyses.py).
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    role: Mapped[AIMessageRole] = mapped_column(
        SqlEnum(AIMessageRole, native_enum=False, length=20),
        nullable=False,
    )

    # 🔒 — основное содержимое сообщения.
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # 🔒 — JSON-снапшот данных, явно прикреплённых пользователем (Manual mode).
    # На этапе 5: профиль и/или анализы. None — данные не прикреплены.
    attached_data: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Маркировка safety-события — заполняется только когда срабатывает протокол.
    # На этапе 5: suicide_risk | medical_emergency. Прочие категории — этап 12.
    safety_event_type: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )

    # Метаданные провайдера ИИ (только для assistant-сообщений).
    provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tokens_used: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    conversation: Mapped[AIConversation] = relationship(back_populates="messages")

    __table_args__ = (
        Index(
            "ix_ai_messages_conversation_created",
            "conversation_id",
            "created_at",
        ),
    )
