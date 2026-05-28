"""telegram_bindings + telegram_binding_codes

Revision ID: 0006_telegram_bindings
Revises: 0005_ai_assistant
Create Date: 2026-05-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_telegram_bindings"
down_revision: str | None = "0005_ai_assistant"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "telegram_bindings",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_username", sa.String(100), nullable=True),
        sa.Column(
            "bound_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "notifications_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "notify_medications",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "notify_visits",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "notify_daily_summary",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "notify_health_tips",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="fk_telegram_bindings_user",
        ),
        sa.UniqueConstraint("user_id", name="uq_telegram_bindings_user"),
        sa.UniqueConstraint(
            "telegram_user_id", name="uq_telegram_bindings_telegram_user"
        ),
    )
    op.create_index(
        "ix_telegram_bindings_user_id", "telegram_bindings", ["user_id"]
    )
    op.create_index(
        "ix_telegram_bindings_telegram_user_id",
        "telegram_bindings",
        ["telegram_user_id"],
    )

    op.create_table(
        "telegram_binding_codes",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("code", sa.String(6), nullable=False),
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
            name="fk_telegram_binding_codes_user",
        ),
        sa.UniqueConstraint("code", name="uq_telegram_binding_codes_code"),
    )
    op.create_index(
        "ix_telegram_binding_codes_user_id",
        "telegram_binding_codes",
        ["user_id"],
    )
    op.create_index(
        "ix_telegram_binding_codes_code",
        "telegram_binding_codes",
        ["code"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_telegram_binding_codes_code", table_name="telegram_binding_codes"
    )
    op.drop_index(
        "ix_telegram_binding_codes_user_id", table_name="telegram_binding_codes"
    )
    op.drop_table("telegram_binding_codes")

    op.drop_index(
        "ix_telegram_bindings_telegram_user_id", table_name="telegram_bindings"
    )
    op.drop_index("ix_telegram_bindings_user_id", table_name="telegram_bindings")
    op.drop_table("telegram_bindings")
