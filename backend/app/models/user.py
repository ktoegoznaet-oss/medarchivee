"""User ORM model.

Schema follows ТЗ v1.1 §5.1. Stage 2 wires up authentication only — fields
related to 2FA and recovery are declared (so we never have to ALTER the table
later) but their write paths are not exercised until stage 7.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import BigInteger, Boolean, DateTime, LargeBinary, String, func
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class UserRole(str, Enum):
    USER = "user"
    ADMIN = "admin"


class UserStatus(str, Enum):
    ACTIVE = "active"
    BLOCKED = "blocked"
    DELETED = "deleted"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    # 32-байтная соль для Argon2id KDF. LargeBinary(32) рендерится как
    # VARBINARY(32) на MariaDB и BLOB на SQLite — что нужно для тестовой БД.
    encryption_salt: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)

    # DEK (Data Encryption Key), зашифрованный KEK из пароля. На identity-режиме
    # — None. На AES-режиме заполняется при регистрации (см. Шаг E).
    encrypted_dek: Mapped[bytes | None] = mapped_column(LargeBinary(255), nullable=True)

    # Recovery-фраза (BIP39): DEK, зашифрованный KEK из мнемонической фразы.
    # recovery_master_key — шифротекст, recovery_phrase_set — флаг наличия,
    # recovery_phrase_lang — язык словаря (russian/english) для UI-подсказок.
    recovery_code_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    recovery_master_key: Mapped[bytes | None] = mapped_column(LargeBinary(255), nullable=True)
    recovery_phrase_set: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    recovery_phrase_lang: Mapped[str | None] = mapped_column(String(8), nullable=True)
    two_factor_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    two_factor_secret: Mapped[str | None] = mapped_column(String(255), nullable=True)

    role: Mapped[UserRole] = mapped_column(
        SqlEnum(UserRole, native_enum=False, length=20),
        default=UserRole.USER,
        nullable=False,
    )
    status: Mapped[UserStatus] = mapped_column(
        SqlEnum(UserStatus, native_enum=False, length=20),
        default=UserStatus.ACTIVE,
        nullable=False,
    )
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
