"""Analysis records and individual measured values.

Tables follow ТЗ v1.1 §5.3 — names are intentionally `analysis_records` and
`analysis_values` (not `analyses` / `analysis_results` from v1.0).

`parameter_code` is **not** encrypted: the dynamics chart groups values by
parameter (`WHERE parameter_code = 'hemoglobin'`), and the indirect leak
«у пользователя есть запись «гемоглобин»» is considered acceptable risk in
exchange for usable time-series queries.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    func,
)
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class AbnormalType(str, Enum):
    LOW = "low"
    HIGH = "high"
    NORMAL = "normal"
    UNKNOWN = "unknown"


class AnalysisRecord(Base):
    __tablename__ = "analysis_records"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Дата сдачи — открытый столбец, нужен для сортировки и фильтра по диапазону.
    analysis_date: Mapped[date] = mapped_column(Date, nullable=False)

    # 🔒-поля
    lab_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    doctor_referral: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )

    values: Mapped[list["AnalysisValue"]] = relationship(
        back_populates="record",
        cascade="all, delete-orphan",
        order_by="AnalysisValue.id",
    )

    __table_args__ = (
        Index("ix_analysis_records_user_date", "user_id", "analysis_date"),
    )


class AnalysisValue(Base):
    __tablename__ = "analysis_values"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    record_id: Mapped[int] = mapped_column(
        ForeignKey("analysis_records.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # user_id дублируется здесь, чтобы фильтр истории параметра шёл одним JOIN-less
    # запросом: `WHERE user_id=? AND parameter_code=?`. Cascade delete по обоим FK
    # гарантирует консистентность.
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Группирующий ключ — НЕ шифруется (см. docstring файла).
    parameter_code: Mapped[str] = mapped_column(String(50), nullable=False)

    # 🔒
    parameter_name: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    unit: Mapped[str] = mapped_column(Text, nullable=False)
    reference_min: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference_max: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_abnormal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    abnormal_type: Mapped[AbnormalType] = mapped_column(
        SqlEnum(AbnormalType, native_enum=False, length=20),
        default=AbnormalType.UNKNOWN,
        nullable=False,
    )

    record: Mapped[AnalysisRecord] = relationship(back_populates="values")

    __table_args__ = (
        Index(
            "ix_analysis_values_user_param_record",
            "user_id",
            "parameter_code",
            "record_id",
        ),
    )
