"""SystemSetting ORM model — простая key-value таблица настроек.

Хранит редактируемые из админ-панели настройки: `registration_mode`,
лимиты из Этапа 9 и т.п. Значение всегда строка (на уровне сервиса
парсится в нужный тип — enum, int, bool).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SystemSetting(Base):
    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(255), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "users.id", ondelete="SET NULL", name="fk_system_settings_updated_by"
        ),
        nullable=True,
    )
