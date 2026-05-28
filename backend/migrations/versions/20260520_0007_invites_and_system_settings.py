"""invite_codes + system_settings

Revision ID: 0007_invites_and_system_settings
Revises: 0006_telegram_bindings
Create Date: 2026-05-20

Шаг D Спринта 1: режимы регистрации (closed/invite_only/open) и
инвайт-коды для закрытой беты. Начальное значение registration_mode —
`invite_only` (см. ТЗ §6.3).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_invites_and_system_settings"
down_revision: str | None = "0006_telegram_bindings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---- system_settings: key-value таблица для редактируемых из админки
    # настроек (registration_mode, лимиты из Этапа 9 и т.п.).
    op.create_table(
        "system_settings",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", sa.String(255), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_by_user_id",
            sa.BigInteger(),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_system_settings_updated_by",
        ),
    )

    # ---- Seed: начальный режим регистрации — invite_only.
    op.execute(
        "INSERT INTO system_settings (key, value, updated_at) "
        "VALUES ('registration_mode', 'invite_only', CURRENT_TIMESTAMP)"
    )

    # ---- invite_codes: одноразовые коды для регистрации в invite_only режиме.
    op.create_table(
        "invite_codes",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("created_by_admin_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used_by_user_id", sa.BigInteger(), nullable=True),
        sa.Column("used_at", sa.DateTime(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("note", sa.String(255), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by_admin_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="fk_invite_codes_admin",
        ),
        sa.ForeignKeyConstraint(
            ["used_by_user_id"],
            ["users.id"],
            ondelete="SET NULL",
            name="fk_invite_codes_used_by",
        ),
        sa.UniqueConstraint("code", name="uq_invite_codes_code"),
    )
    op.create_index("ix_invite_codes_code", "invite_codes", ["code"])
    op.create_index(
        "ix_invite_codes_created_by_admin_id",
        "invite_codes",
        ["created_by_admin_id"],
    )
    op.create_index(
        "ix_invite_codes_used_by_user_id", "invite_codes", ["used_by_user_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_invite_codes_used_by_user_id", table_name="invite_codes")
    op.drop_index(
        "ix_invite_codes_created_by_admin_id", table_name="invite_codes"
    )
    op.drop_index("ix_invite_codes_code", table_name="invite_codes")
    op.drop_table("invite_codes")
    op.drop_table("system_settings")
