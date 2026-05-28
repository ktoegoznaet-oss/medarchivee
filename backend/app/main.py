"""FastAPI application entrypoint."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1 import api_router
from app.config import settings
from app.dependencies import (
    get_admin_notifier,
    reset_arq_email_pool,
    set_arq_email_pool,
)
from app.logging_config import configure_logging
from app.rate_limit import limiter
from app.sentry_init import init_sentry
from app.services.admin_telegram.notifier import format_critical_error
from app.services.encryption_service import SessionKeyNotFoundError

configure_logging()
init_sentry(
    dsn=settings.sentry_dsn,
    environment=settings.app_env,
    traces_sample_rate=settings.sentry_traces_sample_rate,
)
log = structlog.get_logger(__name__)


_DEFAULT_SECRETS = {"change-me", "change-me-in-production-64-chars-min"}


def _assert_production_secrets_strong() -> None:
    """Refuse to start in production with factory-default or short secrets.

    Validators в `config.py` отлавливают это раньше — на этапе чтения env,
    — но валидаторы можно отключить (например, монкипатчингом в тестах),
    поэтому здесь повторная проверка на старте приложения.
    """
    bad: list[str] = []
    if settings.jwt_secret in _DEFAULT_SECRETS or len(settings.jwt_secret) < 32:
        bad.append("JWT_SECRET")
    if settings.secret_key in _DEFAULT_SECRETS or len(settings.secret_key) < 32:
        bad.append("SECRET_KEY")
    if bad:
        log.error("app.startup.weak_secrets", fields=bad)
        raise RuntimeError(
            "Refusing to start in production with weak secrets: "
            f"{', '.join(bad)}. Generate: openssl rand -hex 32"
        )


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Startup / shutdown hooks — заменяет deprecated `on_event`.

    Lifespan-context введён в FastAPI 0.93 как замена `@app.on_event`.
    Здесь же дублируем проверку production-секретов — на случай, если
    pydantic-валидаторы прокинули значения в обход (тесты, монкипатч).

    Дополнительно поднимаем ARQ-pool для постановки email-задач в очередь.
    Pool создаётся один раз на процесс backend и закрывается на shutdown.
    """
    if settings.app_env == "production":
        _assert_production_secrets_strong()
    arq_pool = None
    try:
        arq_pool = await create_pool(
            RedisSettings(
                host=settings.redis_host,
                port=settings.redis_port,
                database=settings.arq_redis_db,
            )
        )
        set_arq_email_pool(arq_pool)
        log.info("app.arq_pool_ready", redis_db=settings.arq_redis_db)
    except Exception as exc:  # noqa: BLE001
        # Не блокируем старт приложения, если ARQ недоступен — email фоллбэк
        # на InProcessQueue + LogEmailSender в dependencies.py.
        log.warning("app.arq_pool_unavailable", error=str(exc))
    log.info(
        "app.startup",
        app_env=settings.app_env,
        encryption_provider=settings.encryption_provider,
    )
    yield
    log.info("app.shutdown")
    if arq_pool is not None:
        await arq_pool.close()
    reset_arq_email_pool()


def create_app() -> FastAPI:
    """FastAPI factory — keeps wiring out of module import side-effects."""
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        docs_url="/docs",
        redoc_url=None,
        lifespan=lifespan,
    )

    # Origin'ы — из ENV (CORS_ORIGINS=...). Дефолт включает localhost для dev,
    # на проде туда подставляется реальный домен.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    async def _session_key_lost(
        _request: Request, _exc: SessionKeyNotFoundError
    ) -> JSONResponse:
        # DEK потерян (Redis_keys рестартился или TTL истёк). Клиент
        # должен попросить пользователя перелогиниться.
        return JSONResponse(
            status_code=401,
            content={"detail": "session_key_lost"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    app.add_exception_handler(SessionKeyNotFoundError, _session_key_lost)

    async def _unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
        # Лог + Sentry (если включён) + Telegram-нотификация админу.
        # Этот handler ловит ТОЛЬКО неожиданные exceptions, не HTTPException
        # — для них FastAPI/Starlette имеет собственный handler, который
        # выставляет правильный status_code. Наш Exception-handler бы их
        # перебил и вернул 500 для любого 404 / 401 / etc.
        if isinstance(exc, (HTTPException, StarletteHTTPException)):
            raise exc
        log.error(
            "app.unhandled_exception",
            path=request.url.path,
            method=request.method,
            error=type(exc).__name__,
            error_msg=str(exc),
        )
        try:
            notifier = get_admin_notifier()
            await notifier.notify(
                format_critical_error(
                    source=f"{request.method} {request.url.path}",
                    message=f"{type(exc).__name__}: {exc}",
                )
            )
        except Exception:  # noqa: BLE001
            pass  # notifier-ошибки не должны затмить исходную
        return JSONResponse(
            status_code=500,
            content={"detail": "internal_server_error"},
        )

    app.add_exception_handler(Exception, _unhandled_exception)

    app.include_router(api_router)

    return app


app = create_app()
