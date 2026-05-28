"""Bot-side copy of the Telegram-related SQLAlchemy models.

Reasons we copy instead of importing from backend (см. подсказку 6.2):
  * бот не зависит от backend как от пакета — деплоится в отдельный
    контейнер с отдельным requirements.txt;
  * меньше surface area: только те поля, что нужны хендлерам.

Если на этапе 10+ копий станет слишком много, выделим общий пакет
`shared_models` и переключим оба сервиса.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    username: Mapped[str] = mapped_column(String(100), nullable=False)


class TelegramBinding(Base):
    __tablename__ = "telegram_bindings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    telegram_username: Mapped[str | None] = mapped_column(
        String(100), nullable=True
    )
    bound_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    notifications_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False
    )
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
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    code: Mapped[str] = mapped_column(String(6), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
