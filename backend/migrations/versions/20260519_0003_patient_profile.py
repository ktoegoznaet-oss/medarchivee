"""patient_profiles + weight_history + chronic_conditions + allergies + family_history

Revision ID: 0003_patient_profile
Revises: 0002_users_and_sessions
Create Date: 2026-05-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_patient_profile"
down_revision: str | None = "0002_users_and_sessions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "patient_profiles",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False, unique=True),
        sa.Column("first_name", sa.Text(), nullable=False),
        sa.Column("last_name", sa.Text(), nullable=False),
        sa.Column("middle_name", sa.Text(), nullable=True),
        sa.Column("birth_date", sa.Text(), nullable=False),
        sa.Column("gender", sa.Text(), nullable=False),
        sa.Column("blood_type", sa.Text(), nullable=True),
        sa.Column("height_cm", sa.Text(), nullable=True),
        sa.Column("weight_kg", sa.Text(), nullable=True),
        sa.Column("emergency_contact", sa.Text(), nullable=True),
        sa.Column("insurance_info", sa.Text(), nullable=True),
        sa.Column("city", sa.Text(), nullable=True),
        sa.Column(
            "timezone",
            sa.String(50),
            nullable=False,
            server_default="Europe/Moscow",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="fk_patient_profiles_user",
        ),
    )
    op.create_index(
        "ix_patient_profiles_user_id",
        "patient_profiles",
        ["user_id"],
        unique=True,
    )

    op.create_table(
        "weight_history",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("weight_kg", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "recorded_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="fk_weight_history_user",
        ),
    )
    op.create_index("ix_weight_history_user_id", "weight_history", ["user_id"])

    op.create_table(
        "chronic_conditions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("icd10_code", sa.Text(), nullable=True),
        sa.Column("diagnosed_at", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
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
            name="fk_chronic_conditions_user",
        ),
    )
    op.create_index(
        "ix_chronic_conditions_user_id",
        "chronic_conditions",
        ["user_id"],
    )

    op.create_table(
        "allergies",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("allergen", sa.Text(), nullable=False),
        sa.Column("reaction", sa.Text(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "severity",
            sa.String(20),
            nullable=False,
            server_default="mild",
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
            name="fk_allergies_user",
        ),
    )
    op.create_index("ix_allergies_user_id", "allergies", ["user_id"])

    op.create_table(
        "family_history",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("relation", sa.Text(), nullable=False),
        sa.Column("condition", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
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
            name="fk_family_history_user",
        ),
    )
    op.create_index("ix_family_history_user_id", "family_history", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_family_history_user_id", table_name="family_history")
    op.drop_table("family_history")
    op.drop_index("ix_allergies_user_id", table_name="allergies")
    op.drop_table("allergies")
    op.drop_index("ix_chronic_conditions_user_id", table_name="chronic_conditions")
    op.drop_table("chronic_conditions")
    op.drop_index("ix_weight_history_user_id", table_name="weight_history")
    op.drop_table("weight_history")
    op.drop_index("ix_patient_profiles_user_id", table_name="patient_profiles")
    op.drop_table("patient_profiles")
