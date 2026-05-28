"""Telegram bot binding ORM models.

Tables follow ТЗ v1.1 §9. На этапе 6:
  * `telegram_bindings`       — связь user ↔ telegram_user_id + флаги уведомлений.
  * `telegram_binding_codes`  — короткоживущие коды для привязки (TTL 10 мин).

Поля не шифруются: `telegram_user_id` нужен для уникального индекса и для
поиска при `/start КОД`; флаги уведомлений — для SQL-выборки кого уведомлять.
Сами по себе они не раскрывают медицинских данных пользователя. Содержимое
уведомлений в БД не хранится: оно собирается в момент отправки.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class TelegramBinding(Base):
    __tablename__ = "telegram_bindings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )
    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, nullable=False, index=True
    )
    # @username хранится без знака @, в нижнем регистре (см. подсказку 6.5).
    telegram_username: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )

    bound_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    # Master switch — выключает все уведомления, не сбрасывая частные флаги.
    notifications_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    # Per-category флаги — реальная отправка по ним идёт с этапов 9–10.
    notify_medications: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    notify_visits: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
    notify_daily_summary: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    notify_health_tips: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )


class TelegramBindingCode(Base):
    __tablename__ = "telegram_binding_codes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 6 цифр, гарантированно ASCII — поэтому String(6) допустим без unicode.
    # Уникальный индекс — чтобы bot мог по коду найти владельца за один SELECT.
    code: Mapped[str] = mapped_column(String(6), unique=True, nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
