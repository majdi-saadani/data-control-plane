"""Application settings, read from environment variables (or a .env file)."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "data-control-plane"
    log_level: str = "INFO"

    # AWS / Kinesis
    aws_region: str = "eu-west-1"
    kinesis_stream_name: str = "energy-sensor-events-dev"

    # Databricks (optional: Databricks endpoints return 503 when not configured)
    databricks_host: str | None = None   # e.g. https://adb-1234567890.12.azuredatabricks.net
    databricks_token: str | None = None
    databricks_timeout_s: float = 30.0

    @property
    def databricks_configured(self) -> bool:
        return bool(self.databricks_host and self.databricks_token)


@lru_cache
def get_settings() -> Settings:
    """Cached settings: read once per process."""
    return Settings()
