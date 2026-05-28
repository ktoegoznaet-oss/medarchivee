"""DashboardService — агрегированные метрики для админ-панели.

Все запросы — COUNT/aggregate, никакого raw-доступа к содержимому
пользователей. Админ видит только числа.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.support import SupportTicket
from app.models.user import User, UserStatus


@dataclass
class DashboardStats:
    users_total: int
    users_active_7d: int  # last_login_at within 7 days
    users_active_30d: int
    users_blocked: int
    users_new_7d: int  # created_at within 7 days
    tickets_total: int
    tickets_new: int
    uploads_size_bytes: int
    activity_by_day: list["DailyCount"]  # last 30 days, новые регистрации


@dataclass
class DailyCount:
    date: str  # ISO date "YYYY-MM-DD"
    count: int


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _calc_dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for entry in path.rglob("*"):
        if entry.is_file():
            try:
                total += entry.stat().st_size
            except OSError:
                pass
    return total


class DashboardService:
    def __init__(self, db: AsyncSession, uploads_root: Path):
        self._db = db
        self._uploads_root = uploads_root

    async def get_stats(self) -> DashboardStats:
        now = _now()
        seven_days_ago = now - timedelta(days=7)
        thirty_days_ago = now - timedelta(days=30)

        users_total = (await self._db.execute(select(func.count(User.id)))).scalar_one()

        users_active_7d = (
            await self._db.execute(
                select(func.count(User.id)).where(
                    User.last_login_at >= seven_days_ago
                )
            )
        ).scalar_one()

        users_active_30d = (
            await self._db.execute(
                select(func.count(User.id)).where(
                    User.last_login_at >= thirty_days_ago
                )
            )
        ).scalar_one()

        users_blocked = (
            await self._db.execute(
                select(func.count(User.id)).where(
                    User.status == UserStatus.BLOCKED
                )
            )
        ).scalar_one()

        users_new_7d = (
            await self._db.execute(
                select(func.count(User.id)).where(
                    User.created_at >= seven_days_ago
                )
            )
        ).scalar_one()

        tickets_total = (
            await self._db.execute(select(func.count(SupportTicket.id)))
        ).scalar_one()

        tickets_new = (
            await self._db.execute(
                select(func.count(SupportTicket.id)).where(
                    SupportTicket.status == "new"
                )
            )
        ).scalar_one()

        # Активность по дням за 30 дней — новые регистрации.
        # GROUP BY date — работает в SQLite и MariaDB через DATE-функцию.
        # SQLAlchemy func.date унифицирует синтаксис.
        rows = await self._db.execute(
            select(
                func.date(User.created_at).label("d"),
                func.count(User.id).label("c"),
            )
            .where(User.created_at >= thirty_days_ago)
            .group_by(func.date(User.created_at))
            .order_by(func.date(User.created_at))
        )
        activity_by_day = [
            DailyCount(date=str(row.d), count=int(row.c)) for row in rows
        ]

        uploads_size_bytes = _calc_dir_size(self._uploads_root)

        return DashboardStats(
            users_total=users_total,
            users_active_7d=users_active_7d,
            users_active_30d=users_active_30d,
            users_blocked=users_blocked,
            users_new_7d=users_new_7d,
            tickets_total=tickets_total,
            tickets_new=tickets_new,
            uploads_size_bytes=uploads_size_bytes,
            activity_by_day=activity_by_day,
        )
