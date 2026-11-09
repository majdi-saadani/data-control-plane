"""Application settings, read from environment variables (or a .env file)."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "data-control-plane"
    log_level: str = "INFO"

    # AWS / Kinesis
    aws_region: str = "eu-west-1"
    kinesis_stream_name: str = "energy-sensor-events-dev"

    # Databricks (optional: Databricks endpoints return 503 when not configured)
    databricks_host: str | None = None   # e.g. https://dbc-1234abcd-5678.cloud.databricks.com
    databricks_token: str | None = None
    databricks_timeout_s: float = 30.0

    # Pipeline orchestration
    pipelines_config_path: str = "config/pipelines.yaml"
    # "dynamodb" in AWS, "memory" for local development without AWS credentials
    tracking_backend: Literal["dynamodb", "memory"] = "dynamodb"
    tracking_table_name: str = "energy-pipeline-runs-dev"
    poll_interval_s: float = 15.0          # how often a running task is polled
    default_task_timeout_min: int = 60     # per-task timeout when the YAML does not set one

    @property
    def databricks_configured(self) -> bool:
        return bool(self.databricks_host and self.databricks_token)


@lru_cache
def get_settings() -> Settings:
    """Cached settings: read once per process."""
    return Settings()
