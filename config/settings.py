"""Глобальные настройки приложения (используем Pydantic BaseSettings)."""

from __future__ import annotations

# Pydantic ≥ 2.5: BaseSettings выделен в отдельный пакет
try:
    from pydantic_settings import BaseSettings  # type: ignore
except ImportError:  # pragma: no cover – пакет может отсутствовать
    from pydantic import BaseSettings  # type: ignore

from pydantic import Field


class Settings(BaseSettings):
    """Читает параметры из переменных окружения или файла .env."""

    QUIK_HOST: str = Field("127.0.0.1", env="QUIK_HOST")
    QUIK_PORT: int = Field(34130, env="QUIK_PORT")

    DATABASE_URL: str = Field("sqlite+aiosqlite:///./arbitrage.db", env="DATABASE_URL")
    BROKER: str = Field("QUIK", env="BROKER")  # на будущее: "BACKTEST"/"DUMMY" и т.д.

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False


settings = Settings()
