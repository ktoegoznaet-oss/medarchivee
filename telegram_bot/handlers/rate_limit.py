"""In-memory rate limit для попыток привязки.

§6.4: не больше 5 неудачных `/start КОД` с одного telegram_user_id в
минуту. Сбрасывается раз в окне; для одного процесса бота этого
достаточно. На этапе 12 при переходе на webhook вынесем в Redis.
"""

from __future__ import annotations

import asyncio
from collections import deque
from time import monotonic


class SlidingWindowLimiter:
    """Простой sliding-window для одного процесса бота.

    Эфемерные `_buckets` могут накапливаться по `telegram_user_id`.
    Чтобы не расти бесконечно (см. W6 в DIAGNOSTIC_REPORT.md), периодически
    подметаем пустые и устаревшие bucket'ы — раз в `_SWEEP_EVERY` вызовов.
    """

    _SWEEP_EVERY = 256

    def __init__(self, *, max_attempts: int, window_seconds: float) -> None:
        self._max = max_attempts
        self._window = window_seconds
        self._buckets: dict[int, deque[float]] = {}
        self._lock = asyncio.Lock()
        self._calls_since_sweep = 0

    async def allow(self, key: int) -> bool:
        now = monotonic()
        async with self._lock:
            bucket = self._buckets.setdefault(key, deque())
            cutoff = now - self._window
            while bucket and bucket[0] < cutoff:
                bucket.popleft()

            self._calls_since_sweep += 1
            if self._calls_since_sweep >= self._SWEEP_EVERY:
                self._sweep(cutoff)
                self._calls_since_sweep = 0

            if len(bucket) >= self._max:
                return False
            bucket.append(now)
            return True

    def _sweep(self, cutoff: float) -> None:
        """Drop empty buckets and buckets whose entries are all expired."""
        to_drop: list[int] = []
        for k, b in self._buckets.items():
            while b and b[0] < cutoff:
                b.popleft()
            if not b:
                to_drop.append(k)
        for k in to_drop:
            del self._buckets[k]


binding_attempt_limiter = SlidingWindowLimiter(max_attempts=5, window_seconds=60.0)
