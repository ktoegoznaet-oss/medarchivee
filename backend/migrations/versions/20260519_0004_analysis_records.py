"""analysis_records + analysis_values

Revision ID: 0004_analysis_records
Revises: 0003_patient_profile
Create Date: 2026-05-19
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_analysis_records"
down_revision: str | None = "0003_patient_profile"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "analysis_records",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("analysis_date", sa.Date(), nullable=False),
        sa.Column("lab_name", sa.Text(), nullable=True),
        sa.Column("doctor_referral", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
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
            name="fk_analysis_records_user",
        ),
    )
    op.create_index(
        "ix_analysis_records_user_id", "analysis_records", ["user_id"]
    )
    op.create_index(
        "ix_analysis_records_user_date",
        "analysis_records",
        ["user_id", "analysis_date"],
    )

    op.create_table(
        "analysis_values",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("record_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("parameter_code", sa.String(50), nullable=False),
        sa.Column("parameter_name", sa.Text(), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("unit", sa.Text(), nullable=False),
        sa.Column("reference_min", sa.Text(), nullable=True),
        sa.Column("reference_max", sa.Text(), nullable=True),
        sa.Column(
            "is_abnormal",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "abnormal_type",
            sa.String(20),
            nullable=False,
            server_default="unknown",
        ),
        sa.ForeignKeyConstraint(
            ["record_id"],
            ["analysis_records.id"],
            ondelete="CASCADE",
            name="fk_analysis_values_record",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="fk_analysis_values_user",
        ),
    )
    op.create_index(
        "ix_analysis_values_record_id", "analysis_values", ["record_id"]
    )
    op.create_index(
        "ix_analysis_values_user_id", "analysis_values", ["user_id"]
    )
    op.create_index(
        "ix_analysis_values_user_param_record",
        "analysis_values",
        ["user_id", "parameter_code", "record_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_analysis_values_user_param_record", table_name="analysis_values"
    )
    op.drop_index("ix_analysis_values_user_id", table_name="analysis_values")
    op.drop_index("ix_analysis_values_record_id", table_name="analysis_values")
    op.drop_table("analysis_values")
    op.drop_index("ix_analysis_records_user_date", table_name="analysis_records")
    op.drop_index("ix_analysis_records_user_id", table_name="analysis_records")
    op.drop_table("analysis_records")
