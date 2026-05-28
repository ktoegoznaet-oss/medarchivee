"""Application configuration loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed view of environment configuration.

    All values are read from a `.env` file in the project root or from the
    surrounding environment. Defaults are safe for local dev only.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- App ---
    app_name: str = Field(default="MedArchive", alias="APP_NAME")
    app_env: Literal["development", "staging", "production"] = Field(
        default="development", alias="APP_ENV"
    )
    debug: bool = Field(default=True, alias="DEBUG")
    secret_key: str = Field(default="change-me", alias="SECRET_KEY")

    # --- Database ---
    db_host: str = Field(default="mariadb", alias="DB_HOST")
    db_port: int = Field(default=3306, alias="DB_PORT")
    db_name: str = Field(default="medarchive", alias="DB_NAME")
    db_user: str = Field(default="medarchive", alias="DB_USER")
    db_password: str = Field(default="medarchive_dev_password", alias="DB_PASSWORD")
    db_root_password: str = Field(default="root_dev_password", alias="DB_ROOT_PASSWORD")

    # --- Redis ---
    redis_host: str = Field(default="redis", alias="REDIS_HOST")
    redis_port: int = Field(default=6379, alias="REDIS_PORT")

    # --- JWT (used from stage 2) ---
    jwt_secret: str = Field(default="change-me", alias="JWT_SECRET")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_access_token_expire_minutes: int = Field(
        default=30, alias="JWT_ACCESS_TOKEN_EXPIRE_MINUTES"
    )
    jwt_refresh_token_expire_days: int = Field(
        default=7, alias="JWT_REFRESH_TOKEN_EXPIRE_DAYS"
    )

    # --- Encryption (used from stage 1) ---
    encryption_provider: Literal["identity", "aesgcm"] = Field(
        default="identity", alias="ENCRYPTION_PROVIDER"
    )

    # --- Argon2id KDF parameters ---
    # OWASP L1 default (m=46MiB, t=1, p=1, ~50ms на 3-CPU/8GB). Можно
    # подкрутить после benchmark на боевом железе — параметры читаются
    # из .env, в коде ничего менять не нужно.
    argon2_memory_kib: int = Field(default=47104, alias="ARGON2_MEMORY_KIB")
    argon2_time_cost: int = Field(default=1, alias="ARGON2_TIME_COST")
    argon2_parallelism: int = Field(default=1, alias="ARGON2_PARALLELISM")

    # --- Redis для сессионных ключей (отдельный инстанс БЕЗ persistence!) ---
    # На рестарт redis_keys теряет все ключи → пользователям нужно
    # перелогиниться. Это безопасное поведение: ключи никогда не уходят
    # на диск, а компрометация дампа диска не даст расшифровать данные.
    redis_keys_host: str = Field(default="redis_keys", alias="REDIS_KEYS_HOST")
    redis_keys_port: int = Field(default=6379, alias="REDIS_KEYS_PORT")
    redis_keys_db: int = Field(default=0, alias="REDIS_KEYS_DB")

    # --- Admin bootstrap ---
    # Пользователь, зарегистрированный с этим email, получает роль ADMIN
    # автоматически. Пустая строка отключает автоназначение — все новые
    # пользователи получают роль USER. Сравнение case-insensitive по email.
    initial_admin_email: str = Field(default="", alias="INITIAL_ADMIN_EMAIL")

    # --- SMTP / email delivery ---
    # Если smtp_user пустой — отправка фоллбэчится в логи (dev/CI режим).
    # В production пустой smtp_user блокирует старт через валидатор ниже.
    smtp_host: str = Field(default="smtp.yandex.ru", alias="SMTP_HOST")
    smtp_port: int = Field(default=465, alias="SMTP_PORT")
    smtp_user: str = Field(default="", alias="SMTP_USER")
    smtp_password: str = Field(default="", alias="SMTP_PASSWORD")
    smtp_from_email: str = Field(default="", alias="SMTP_FROM_EMAIL")
    smtp_from_name: str = Field(default="MedArchive", alias="SMTP_FROM_NAME")
    smtp_use_ssl: bool = Field(default=True, alias="SMTP_USE_SSL")
    smtp_timeout_seconds: int = Field(default=30, alias="SMTP_TIMEOUT_SECONDS")

    # Frontend base URL — используется в письмах (ссылка на UI, например
    # "перейдите на страницу подтверждения и введите код"). Должен быть
    # доступен из браузеров пользователей.
    frontend_base_url: str = Field(
        default="http://localhost", alias="FRONTEND_BASE_URL"
    )

    # --- ARQ (Redis-based async task queue) ---
    # Отдельная DB в том же Redis-инстансе, чтобы не путаться с кэшом.
    arq_redis_db: int = Field(default=1, alias="ARQ_REDIS_DB")

    # --- Uploads ---
    # Корневая директория пользовательских файлов (скриншоты тикетов и т.п.).
    # В docker-compose монтируется как volume, чтобы файлы переживали
    # рестарт контейнера.
    uploads_root: str = Field(default="/app/uploads", alias="UPLOADS_ROOT")

    # --- AI assistant (used from stage 5) ---
    # Пустая строка — допустимо в dev/CI: тесты замокают провайдера, реальный
    # запрос наружу не уйдёт. В проде/деве с живым Gemini нужно положить ключ
    # в .env.
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    gemini_model: str = Field(
        default="gemini-1.5-flash", alias="GEMINI_MODEL"
    )
    gemini_temperature: float = Field(
        default=0.4, alias="GEMINI_TEMPERATURE"
    )
    gemini_max_output_tokens: int = Field(
        default=1024, alias="GEMINI_MAX_OUTPUT_TOKENS"
    )
    gemini_timeout_seconds: int = Field(
        default=30, alias="GEMINI_TIMEOUT_SECONDS"
    )

    # --- Telegram bot (used from stage 6) ---
    # Токен можно оставить пустым в CI/dev без живого бота — тесты замокают
    # отправку через httpx-respx; в проде/деве с живым ботом подставь токен
    # от BotFather.
    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    telegram_bot_username: str = Field(
        default="medarchive_bot", alias="TELEGRAM_BOT_USERNAME"
    )

    # --- Admin Telegram bot (отдельный от пользовательского) ---
    # Бот для уведомлений админа о регистрациях/тикетах/ошибках и
    # команд /stats /health /help. Получить токен у @BotFather и
    # узнать chat_id (например, через @userinfobot после /start).
    # Пустой токен → no-op notifier, бот-сервис тогда не нужен.
    telegram_admin_bot_token: str = Field(
        default="", alias="TELEGRAM_ADMIN_BOT_TOKEN"
    )
    telegram_admin_chat_id: str = Field(
        default="", alias="TELEGRAM_ADMIN_CHAT_ID"
    )

    # --- Sentry / GlitchTip error tracking ---
    # GlitchTip — open-source, Sentry-совместимый. Self-host'ится отдельно
    # (см. docs/DEPLOY.md). Пустой DSN отключает sentry-SDK полностью.
    sentry_dsn: str = Field(default="", alias="SENTRY_DSN")
    # 0.0 — выключает performance monitoring (отправляет только errors).
    # Для приватности мы не хотим отправлять трейсы с payload запросов.
    sentry_traces_sample_rate: float = Field(
        default=0.0, alias="SENTRY_TRACES_SAMPLE_RATE"
    )

    # --- CORS ---
    # CSV-список origin'ов, которым разрешён доступ к API. На проде заменяется
    # на реальный домен. Если не задано — используем dev-defaults (localhost).
    cors_origins_raw: str = Field(
        default="http://localhost,http://localhost:80,http://localhost:5173,"
        "http://127.0.0.1,http://127.0.0.1:5173",
        alias="CORS_ORIGINS",
    )

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_origins_raw.split(",") if o.strip()]

    # ----- Security validators ------------------------------------------- #

    @field_validator("jwt_secret", "secret_key")
    @classmethod
    def _reject_default_secret_in_prod(cls, value: str, info) -> str:  # type: ignore[no-untyped-def]
        """Запрещаем заводские секреты, когда APP_ENV=production.

        В dev/staging — допускаем заглушки: разработчик не должен генерить
        случайный secret для локального запуска.
        """
        import os

        if os.getenv("APP_ENV", "development") != "production":
            return value
        defaults = {"change-me", "change-me-in-production-64-chars-min"}
        if value in defaults or len(value) < 32:
            raise ValueError(
                f"{info.field_name} must be at least 32 chars and not a "
                "factory default in production. "
                "Generate one: openssl rand -hex 32"
            )
        return value

    @field_validator("smtp_user")
    @classmethod
    def _require_smtp_in_prod(cls, value: str, info) -> str:  # type: ignore[no-untyped-def]
        """В production пустой SMTP_USER блокирует старт.

        В dev/staging — допускаем пустоту: отправитель писем фоллбэчится
        в структурный лог (см. `email.LogSmtpSender`). Это позволяет
        крутить локалку без обязательного SMTP-аккаунта.
        """
        import os

        if os.getenv("APP_ENV", "development") != "production":
            return value
        if not value.strip():
            raise ValueError(
                f"{info.field_name} must be set in production — "
                "configure Yandex SMTP credentials or другой провайдер."
            )
        return value

    @property
    def arq_redis_settings(self) -> dict[str, object]:
        """Map for arq.RedisSettings — keeps coupling to arq out of config."""
        return {
            "host": self.redis_host,
            "port": self.redis_port,
            "database": self.arq_redis_db,
        }

    @property
    def database_url(self) -> str:
        """Async SQLAlchemy URL for MariaDB via asyncmy."""
        return (
            f"mysql+asyncmy://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}?charset=utf8mb4"
        )

    @property
    def redis_url(self) -> str:
        return f"redis://{self.redis_host}:{self.redis_port}/0"

    @property
    def redis_keys_url(self) -> str:
        return f"redis://{self.redis_keys_host}:{self.redis_keys_port}/{self.redis_keys_db}"


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor — safe to call from anywhere."""
    return Settings()


settings = get_settings()
