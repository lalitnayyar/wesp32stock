"""Environment-driven settings. Runtime-tunable settings live in the database (see settings_store)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_REPO_SHARED = Path(__file__).resolve().parents[3] / "shared"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = Field("development", description="development | test | production")
    app_secret_key: str = "change-me-insecure-development-key-000000"
    database_url: str = "sqlite:///./lalitstock.db"

    admin_username: str = "admin"
    admin_password: str | None = None  # bootstrap password for the first admin only

    market_provider: str = "yahoo"  # yahoo | fixture
    scheduler_enabled: bool = True
    simulator_enabled: bool | None = None  # default: enabled outside production

    shared_dir: Path = _REPO_SHARED
    session_hours: int = 12
    cookie_secure: bool = False
    cors_origins: str = ""  # comma-separated; empty = same-origin only
    log_level: str = "INFO"

    @field_validator("simulator_enabled", "admin_password", mode="before")
    @classmethod
    def _blank_is_none(cls, v):
        return None if isinstance(v, str) and not v.strip() else v

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def simulator_active(self) -> bool:
        if self.simulator_enabled is None:
            return not self.is_production
        return self.simulator_enabled


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if s.is_production and (s.app_secret_key.startswith("change-me") or len(s.app_secret_key) < 32):
        raise RuntimeError("APP_SECRET_KEY must be set to a random value of at least 32 characters in production")
    return s
