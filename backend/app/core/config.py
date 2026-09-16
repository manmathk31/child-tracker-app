"""Application configuration management via pydantic-settings."""

from functools import lru_cache
from typing import List, Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central application settings validated at startup."""

    # Environment
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    DEBUG: bool = True
    APP_NAME: str = "ChildTrack"
    APP_VERSION: str = "0.1.0"

    # Server Binding
    HOST: str = "127.0.0.1"
    PORT: int = 8000

    # Database
    DATABASE_URL: str = Field(
        default="sqlite+aiosqlite:///./childtrack_dev.db",
        description="Async SQLAlchemy database connection string",
    )

    # Security & Authentication
    SECRET_KEY: str = Field(
        default="insecure-dev-secret-key-change-in-production-minimum-32-chars",
        description="Secret key for signing JWT tokens",
    )
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Logging
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    LOG_JSON_FORMAT: bool = False

    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:8000", "http://127.0.0.1:8000"]

    # Organization / School Settings Defaults (overridden by DB settings once configured)
    DEFAULT_TIMEZONE: str = "UTC"

    # Alert Threshold Defaults
    DEFAULT_OFFLINE_THRESHOLD_MINUTES: int = 5
    DEFAULT_CRITICAL_OFFLINE_THRESHOLD_MINUTES: int = 15
    DEFAULT_LOW_BATTERY_PERCENT: int = 20
    DEFAULT_MIN_LOCALIZATION_CONFIDENCE: float = 0.45

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    @property
    def is_production(self) -> bool:
        """Return True if running in production mode."""
        return self.ENVIRONMENT == "production"

    @property
    def is_sqlite(self) -> bool:
        """Return True if using SQLite database."""
        return self.DATABASE_URL.startswith("sqlite")


@lru_cache()
def get_settings() -> Settings:
    """Return a cached singleton instance of application settings."""
    return Settings()
