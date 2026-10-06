"""Environment configuration, validated once at startup.

Every secret comes from the environment (or a git-ignored `.env`); nothing sensitive has a default.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PLACEHOLDER = "CHANGE_ME"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    database_url: str
    migration_database_url: str | None = None
    session_ttl_minutes: int = Field(60, ge=5, le=24 * 60)
    login_max_failures: int = Field(5, ge=3, le=20)
    login_lock_minutes: int = Field(15, ge=1, le=24 * 60)
    cookie_secure: bool = False
    bcrypt_rounds: int = Field(12, ge=4, le=15)   # 4 only in tests; 12 is the production-grade cost
    login_ip_limit: int = Field(20, ge=1)         # login attempts per IP per minute (in-process throttle)
    log_level: str = "INFO"
    seed_user_password: str | None = None
    app_db_password: str | None = None            # only read by `scripts/db.py bootstrap`, never by the running app

    @model_validator(mode="after")
    def _production_must_be_hardened(self) -> "Settings":
        if self.app_env == "production":
            if not self.cookie_secure:
                raise ValueError("COOKIE_SECURE must be true when APP_ENV=production")
            if PLACEHOLDER in self.database_url:
                raise ValueError("DATABASE_URL still contains the CHANGE_ME placeholder")
        return self

    @property
    def owner_database_url(self) -> str:
        """Connection used for migrations and seeding (schema owner)."""
        return self.migration_database_url or self.database_url


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # values come from the environment
