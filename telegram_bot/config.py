"""Telegram-bot configuration — independent Settings so we don't pull in
the backend package. Mirrors a subset of `backend/app/config.py`.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    telegram_bot_username: str = Field(
        default="medarchive_bot", alias="TELEGRAM_BOT_USERNAME"
    )

    db_host: str = Field(default="mariadb", alias="DB_HOST")
    db_port: int = Field(default=3306, alias="DB_PORT")
    db_name: str = Field(default="medarchive", alias="DB_NAME")
    db_user: str = Field(default="medarchive", alias="DB_USER")
    db_password: str = Field(
        default="medarchive_dev_password", alias="DB_PASSWORD"
    )

    @property
    def database_url(self) -> str:
        return (
            f"mysql+asyncmy://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}?charset=utf8mb4"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
