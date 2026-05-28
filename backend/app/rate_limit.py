"""SlowAPI limiter shared across the app.

We keep the `Limiter` instance in its own module so it can be:
  * registered as middleware in `main.py`,
  * imported by individual routers to apply `@limiter.limit(...)` decorators,
  * monkey-patched off in tests.
"""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
