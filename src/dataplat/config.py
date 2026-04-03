"""Centralized configuration via pydantic-settings.

All environment variables are validated on import. Missing required
values raise immediately — no silent failures at query time.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """DataPlat configuration — loaded from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Schwab ──────────────────────────────────────────────
    schwab_app_key: str = ""
    schwab_app_secret: str = ""
    schwab_redirect_uri: str = "https://127.0.0.1"
    schwab_tokens_db: str = ".schwab_tokens.db"

    # ── ClickHouse ──────────────────────────────────────────
    clickhouse_host: str = "localhost"
    clickhouse_port: int = 8123
    clickhouse_user: str = "default"
    clickhouse_password: str = ""
    clickhouse_database: str = "dataplat"

    # ── Polygon (reference data + one-off backfill only) ────
    polygon_api_key: str = ""

    # ── FRED ────────────────────────────────────────────────
    fred_api_key: str = ""


# Module-level singleton — import this everywhere.
settings = Settings()
