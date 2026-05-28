"""Reference data lookup — ICD-10 (Russian, minimal subset).

Справочник кэшируется в памяти процесса (singleton, ленивая загрузка из JSON
в `app/data/icd10_ru.json`). Это **не** содержимое пользователя, поэтому
шифровать его не требуется. Запросы дополнительно кэшируются в Redis на 1
час — для тестов и dev-режима без Redis есть мягкий fallback.
"""

from __future__ import annotations

import json
import time
from functools import lru_cache
from pathlib import Path

import structlog
from redis import asyncio as aioredis
from redis.exceptions import RedisError

from app.config import settings
from app.schemas.profile import ICD10Entry

log = structlog.get_logger(__name__)

_ICD10_PATH = Path(__file__).resolve().parent.parent / "data" / "icd10_ru.json"
_CACHE_TTL_SECONDS = 3600


@lru_cache(maxsize=1)
def _load_icd10() -> tuple[ICD10Entry, ...]:
    raw = json.loads(_ICD10_PATH.read_text(encoding="utf-8"))
    return tuple(ICD10Entry(**entry) for entry in raw)


def _matches(query: str, entry: ICD10Entry) -> bool:
    q = query.lower()
    return q in entry.code.lower() or q in entry.name.lower()


class DictionariesService:
    """Stateless: holds either a redis client for cache or `None` for dev."""

    def __init__(self, redis_client: aioredis.Redis | None = None):
        self._redis = redis_client

    async def search_icd10(self, query: str, limit: int = 20) -> list[ICD10Entry]:
        query = query.strip()
        if not query:
            return []
        cache_key = f"icd10:{query.lower()}:{limit}"
        if self._redis is not None:
            cached = await self._safe_redis_get(cache_key)
            if cached is not None:
                return [ICD10Entry(**item) for item in json.loads(cached)]

        results = [entry for entry in _load_icd10() if _matches(query, entry)][:limit]

        if self._redis is not None:
            payload = json.dumps([r.model_dump() for r in results], ensure_ascii=False)
            await self._safe_redis_set(cache_key, payload)
        return results

    async def _safe_redis_get(self, key: str) -> str | None:
        try:
            return await self._redis.get(key)  # type: ignore[union-attr]
        except RedisError as exc:
            log.warning("dictionaries.redis_get_failed", error=str(exc))
            return None

    async def _safe_redis_set(self, key: str, value: str) -> None:
        try:
            await self._redis.set(key, value, ex=_CACHE_TTL_SECONDS)  # type: ignore[union-attr]
        except RedisError as exc:
            log.warning("dictionaries.redis_set_failed", error=str(exc))


def build_dictionaries_service() -> DictionariesService:
    """Build a service with the shared Redis client (or `None` when unavailable)."""
    try:
        client = aioredis.from_url(
            settings.redis_url, encoding="utf-8", decode_responses=True
        )
    except Exception as exc:  # noqa: BLE001 — dev fallback
        log.warning("dictionaries.redis_unavailable", error=str(exc))
        client = None
    return DictionariesService(client)


# In-process timestamp tracking is only used by tests that need to invalidate.
_last_loaded_at = time.time()
