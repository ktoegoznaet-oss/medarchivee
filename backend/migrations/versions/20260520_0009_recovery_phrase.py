"""users.recovery_phrase_lang + recovery_phrase_set + wipe_codes

Revision ID: 0009_recovery_phrase
Revises: 0008_encrypted_dek
Create Date: 2026-05-20

Шаг F Спринта 2: BIP39 мнемоника как второй путь восстановления DEK.

users.recovery_phrase_lang — какой язык словаря выбрал пользователь
  (russian/english). Хранится чтобы при восстановлении подсказывать
  юзеру в каком словаре искать слова при опечатках.
users.recovery_phrase_set — флаг, что recovery_master_key заполнен.
  Используется UI как сигнал "после первого логина показать страницу
  с фразой".

account_wipe_codes — таблица для flow "у меня нет фразы → удалить
  аккаунт". Одноразовый код, 30 минут жизни, обязательное
  подтверждение через email.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_recovery_phrase"
down_revision: str | None = "0008_encrypted_dek"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("recovery_phrase_lang", sa.String(8), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "recovery_phrase_set",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )

    op.create_table(
        "account_wipe_codes",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("code", sa.String(8), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column(
            "used",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="fk_account_wipe_codes_user",
        ),
    )
    op.create_index(
        "ix_account_wipe_codes_user_id", "account_wipe_codes", ["user_id"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_account_wipe_codes_user_id", table_name="account_wipe_codes"
    )
    op.drop_table("account_wipe_codes")
    op.drop_column("users", "recovery_phrase_set")
    op.drop_column("users", "recovery_phrase_lang")
