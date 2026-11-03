"""FastAPI dependency injection: builds services from Settings.

Tests replace these functions via `app.dependency_overrides`.
"""

from typing import Annotated

from fastapi import Depends

from app.clients.databricks_client import DatabricksClient
from app.clients.kinesis_client import KinesisClient
from app.core.config import Settings, get_settings
from app.core.exceptions import ServiceNotConfiguredError
from app.services.databricks_runner import DatabricksRunnerService
from app.services.event_sender import EventSenderService

SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_event_sender(settings: SettingsDep) -> EventSenderService:
    kinesis = KinesisClient(stream_name=settings.kinesis_stream_name, region=settings.aws_region)
    return EventSenderService(kinesis)


def get_databricks_runner(settings: SettingsDep) -> DatabricksRunnerService:
    if not settings.databricks_configured:
        raise ServiceNotConfiguredError("Databricks is not configured (DATABRICKS_HOST / DATABRICKS_TOKEN)")
    client = DatabricksClient(
        host=settings.databricks_host,
        token=settings.databricks_token,
        timeout_s=settings.databricks_timeout_s,
    )
    return DatabricksRunnerService(client)


EventSenderDep = Annotated[EventSenderService, Depends(get_event_sender)]
DatabricksRunnerDep = Annotated[DatabricksRunnerService, Depends(get_databricks_runner)]
