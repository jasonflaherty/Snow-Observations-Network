from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://son:son@localhost:5432/son"
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    son_user_agent: str = (
        "SnowObservationsNetwork/0.1 "
        "(+https://github.com/jasonflaherty/Snow-Observations-Network)"
    )
    anon_rate_limit_per_day: int = 1000
    son_free_key: str = "change-me-free"
    son_research_key: str = "change-me-research"
    son_pro_key: str = "change-me-pro"

    raw_storage_path: str = "storage/raw"

    # Comma-separated browser origins allowed to call the API (GitHub Pages, local preview)
    cors_origins: str = (
        "https://jasonflaherty.github.io,"
        "http://localhost:8080,"
        "http://127.0.0.1:8080,"
        "http://localhost:5500,"
        "http://127.0.0.1:5500"
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
