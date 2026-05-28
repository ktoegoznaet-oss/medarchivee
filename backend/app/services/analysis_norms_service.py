"""Reference dictionary of lab parameters and their norms (RU).

`analysis_norms.json` is loaded once at process startup. Each parameter carries
a list of `norms` entries keyed by gender + age range. `get_norm(...)` picks
the most-specific match for the user; `search(...)` is used by the autocomplete.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import structlog
from pydantic import BaseModel, ConfigDict
from redis import asyncio as aioredis
from redis.exceptions import RedisError

from app.config import settings

log = structlog.get_logger(__name__)

_NORMS_PATH = Path(__file__).resolve().parent.parent / "data" / "analysis_norms.json"
_CACHE_TTL_SECONDS = 3600


class NormRange(BaseModel):
    model_config = ConfigDict(extra="ignore")
    gender: str  # "male" | "female" | "any"
    age_from: int
    age_to: int
    min: float | None = None
    max: float | None = None


class ParameterDef(BaseModel):
    model_config = ConfigDict(extra="ignore")
    code: str
    name_ru: str
    name_en: str
    unit: str
    alternative_units: list[str] = []
    category: str
    description: str | None = None
    synonyms: list[str] = []
    norms: list[NormRange]


class ParameterSummary(BaseModel):
    """Compact view for autocomplete."""

    code: str
    name_ru: str
    unit: str
    category: str


@lru_cache(maxsize=1)
def _load_parameters() -> tuple[ParameterDef, ...]:
    raw = json.loads(_NORMS_PATH.read_text(encoding="utf-8"))
    items = []
    for code, body in raw.items():
        items.append(ParameterDef(code=code, **body))
    return tuple(items)


def _match_norm(norms: list[NormRange], gender: str, age: int) -> NormRange | None:
    # Точное совпадение по полу + возрасту > совпадение по "any" + возрасту
    # > совпадение только по полу.
    candidates: list[NormRange] = []
    for norm in norms:
        in_age = norm.age_from <= age <= norm.age_to
        if not in_age:
            continue
        if norm.gender == gender:
            return norm
        if norm.gender == "any":
            candidates.append(norm)
    return candidates[0] if candidates else None


class AnalysisNormsService:
    def __init__(self, redis_client: aioredis.Redis | None = None):
        self._redis = redis_client

    def all_parameters(self) -> tuple[ParameterDef, ...]:
        return _load_parameters()

    def get(self, code: str) -> ParameterDef | None:
        for item in _load_parameters():
            if item.code == code:
                return item
        return None

    def get_norm(self, code: str, gender: str, age: int) -> NormRange | None:
        param = self.get(code)
        if param is None:
            return None
        return _match_norm(param.norms, gender=gender, age=age)

    async def search(self, query: str, limit: int = 20) -> list[ParameterSummary]:
        query = query.strip()
        if not query:
            return []
        cache_key = f"analysis_norms:search:{query.lower()}:{limit}"
        cached = await self._safe_redis_get(cache_key)
        if cached is not None:
            return [ParameterSummary.model_validate(item) for item in json.loads(cached)]

        q = query.lower()
        results: list[ParameterSummary] = []
        for item in _load_parameters():
            haystack = [
                item.name_ru.lower(),
                item.name_en.lower(),
                item.code.lower(),
                *(s.lower() for s in item.synonyms),
            ]
            if any(q in h for h in haystack):
                results.append(
                    ParameterSummary(
                        code=item.code,
                        name_ru=item.name_ru,
                        unit=item.unit,
                        category=item.category,
                    )
                )
                if len(results) >= limit:
                    break

        payload = json.dumps(
            [r.model_dump() for r in results], ensure_ascii=False
        )
        await self._safe_redis_set(cache_key, payload)
        return results

    async def _safe_redis_get(self, key: str) -> str | None:
        if self._redis is None:
            return None
        try:
            return await self._redis.get(key)
        except RedisError as exc:
            log.warning("analysis_norms.redis_get_failed", error=str(exc))
            return None

    async def _safe_redis_set(self, key: str, value: str) -> None:
        if self._redis is None:
            return
        try:
            await self._redis.set(key, value, ex=_CACHE_TTL_SECONDS)
        except RedisError as exc:
            log.warning("analysis_norms.redis_set_failed", error=str(exc))


def build_analysis_norms_service() -> AnalysisNormsService:
    try:
        client = aioredis.from_url(
            settings.redis_url, encoding="utf-8", decode_responses=True
        )
    except Exception as exc:  # noqa: BLE001 — dev fallback
        log.warning("analysis_norms.redis_unavailable", error=str(exc))
        client = None
    return AnalysisNormsService(client)
