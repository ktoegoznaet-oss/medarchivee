"""AccountWipeCode — одноразовый код для удаления аккаунта без recovery-фразы.

Flow: пользователь забыл и пароль, и фразу → запрашивает удаление аккаунта.
Сервер отправляет 8-значный код на email пользователя. Подтверждение кода
полностью удаляет аккаунт (CASCADE по FK на users.id).

Это не альтернатива восстановления — данные восстановить нельзя. Это
явный «нажми чтобы навсегда стереть».
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AccountWipeCode(Base):
    __tablename__ = "account_wipe_codes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE", name="fk_account_wipe_codes_user"),
        nullable=False,
        index=True,
    )
    code: Mapped[str] = mapped_column(String(8), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
