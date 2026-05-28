"""Service health endpoint — pings DB and Redis."""

from __future__ import annotations

from functools import lru_cache

import structlog
from fastapi import APIRouter, Depends
from redis import asyncio as aioredis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db

router = APIRouter()
log = structlog.get_logger(__name__)

APP_VERSION = "0.1.0"


@lru_cache(maxsize=1)
def _health_redis() -> aioredis.Redis:
    """Shared async Redis client for the health probe.

    Liveness-probe бьёт раз в 10 секунд — создавать новое подключение
    каждый вызов затратно (см. W9 в DIAGNOSTIC_REPORT.md). Держим один
    клиент на процесс.
    """
    return aioredis.from_url(
        settings.redis_url, encoding="utf-8", decode_responses=True
    )


async def _check_db(db: AsyncSession) -> bool:
    try:
        result = await db.execute(text("SELECT 1"))
        return result.scalar() == 1
    except Exception as exc:  # noqa: BLE001 — health check intentionally swallows
        log.warning("health.db_check_failed", error=str(exc))
        return False


async def _check_redis() -> bool:
    try:
        pong = await _health_redis().ping()
        return bool(pong)
    except Exception as exc:  # noqa: BLE001
        log.warning("health.redis_check_failed", error=str(exc))
        return False


@router.get("/health")
async def health(db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    """Liveness + readiness probe.

    Returns `status: ok` only when both DB and Redis answer; otherwise
    `status: degraded` with per-component flags.
    """
    db_ok = await _check_db(db)
    redis_ok = await _check_redis()
    return {
        "status": "ok" if (db_ok and redis_ok) else "degraded",
        "version": APP_VERSION,
        "db": "ok" if db_ok else "fail",
        "redis": "ok" if redis_ok else "fail",
    }
