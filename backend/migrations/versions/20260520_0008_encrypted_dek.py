"""users.encrypted_dek + redis_keys notes

Revision ID: 0008_encrypted_dek
Revises: 0007_invites_and_system_settings
Create Date: 2026-05-20

Шаг E Спринта 2: двухслойная архитектура шифрования (DEK + KEK).
Добавляем колонку encrypted_dek — DEK, зашифрованный KEK, который
выводится из пароля через Argon2id.

DEK (Data Encryption Key) — случайные 32 байта, генерируются один
раз при регистрации. Им шифруются все медданные. Никогда не меняется.

KEK (Key Encryption Key) — производный от пароля + соли. Меняется
при смене пароля; перешифровывается только encrypted_dek, а не
все данные пользователя.

Поле recovery_master_key (уже есть в users) — DEK, зашифрованный
KEK, выведенным из BIP39-фразы (наполняется в Шаге F).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_encrypted_dek"
down_revision: str | None = "0007_invites_and_system_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # nullable=True потому что:
    #   1) для существующих пользователей (если есть) DEK не сгенерирован
    #      — они получат его при следующем логине, либо мы сбросим базу
    #      перед включением AES (см. DEPLOY.md);
    #   2) колонка не относится к чувствительным секретам — это
    #      шифротекст DEK, бесполезный без KEK из пароля.
    op.add_column(
        "users",
        sa.Column("encrypted_dek", sa.LargeBinary(255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "encrypted_dek")
