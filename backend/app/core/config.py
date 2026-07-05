"""Typed application configuration."""

from functools import lru_cache

from pydantic import Field, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """RelayGuard runtime settings."""

    app_name: str = "RelayGuard API"
    app_version: str = "0.1.0"
    environment: str = "local"
    postgres_db: str = "relayguard"
    postgres_user: str = "relayguard"
    postgres_password: str = Field(default="relayguard", repr=False)
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    model_config = SettingsConfigDict(
        env_file="../.env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def database_url(self) -> str:
        """Build an asyncpg SQLAlchemy URL from discrete PostgreSQL settings."""
        return str(
            PostgresDsn.build(
                scheme="postgresql+asyncpg",
                username=self.postgres_user,
                password=self.postgres_password,
                host=self.postgres_host,
                port=self.postgres_port,
                path=self.postgres_db,
            )
        )


@lru_cache
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
