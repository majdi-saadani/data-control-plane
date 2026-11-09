"""FastAPI dependency injection: builds services from Settings.

Tests replace these functions via `app.dependency_overrides`.
Long-lived objects (pipeline registry, tracking repository) are cached per process.
"""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends

from app.clients.databricks_client import DatabricksClient
from app.clients.kinesis_client import KinesisClient
from app.clients.lambda_client import LambdaClient
from app.core.config import Settings, get_settings
from app.core.exceptions import ServiceNotConfiguredError
from app.repositories.tracking_repository import (
    DynamoDBTrackingRepository,
    InMemoryTrackingRepository,
    TrackingRepository,
)
from app.services.databricks_runner import DatabricksRunnerService
from app.services.event_sender import EventSenderService
from app.services.pipeline_orchestrator import PipelineOrchestrator
from app.services.pipeline_registry import PipelineRegistry
from app.services.task_executors import DatabricksJobExecutor, LambdaExecutor, TaskExecutor

SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_event_sender(settings: SettingsDep) -> EventSenderService:
    kinesis = KinesisClient(stream_name=settings.kinesis_stream_name, region=settings.aws_region)
    return EventSenderService(kinesis)


def _databricks_client(settings: Settings) -> DatabricksClient:
    if not settings.databricks_configured:
        raise ServiceNotConfiguredError("Databricks is not configured (DATABRICKS_HOST / DATABRICKS_TOKEN)")
    return DatabricksClient(
        host=settings.databricks_host,
        token=settings.databricks_token,
        timeout_s=settings.databricks_timeout_s,
    )


def get_databricks_runner(settings: SettingsDep) -> DatabricksRunnerService:
    return DatabricksRunnerService(_databricks_client(settings))


@lru_cache
def _registry(path: str) -> PipelineRegistry:
    return PipelineRegistry.from_yaml(path)


def get_pipeline_registry(settings: SettingsDep) -> PipelineRegistry:
    return _registry(settings.pipelines_config_path)


@lru_cache
def _repository(backend: str, table_name: str, region: str) -> TrackingRepository:
    if backend == "memory":
        return InMemoryTrackingRepository()
    return DynamoDBTrackingRepository(table_name=table_name, region=region)


def get_tracking_repository(settings: SettingsDep) -> TrackingRepository:
    return _repository(settings.tracking_backend, settings.tracking_table_name, settings.aws_region)


def get_orchestrator(settings: SettingsDep) -> PipelineOrchestrator:
    executors: dict[str, TaskExecutor] = {
        "lambda": LambdaExecutor(LambdaClient(region=settings.aws_region)),
    }
    if settings.databricks_configured:
        # Without Databricks credentials, pipelines containing databricks_job tasks return 503 at start
        executors["databricks_job"] = DatabricksJobExecutor(_databricks_client(settings), settings.poll_interval_s)
    return PipelineOrchestrator(
        registry=get_pipeline_registry(settings),
        repository=get_tracking_repository(settings),
        executors=executors,
        default_task_timeout_min=settings.default_task_timeout_min,
    )


EventSenderDep = Annotated[EventSenderService, Depends(get_event_sender)]
DatabricksRunnerDep = Annotated[DatabricksRunnerService, Depends(get_databricks_runner)]
PipelineRegistryDep = Annotated[PipelineRegistry, Depends(get_pipeline_registry)]
OrchestratorDep = Annotated[PipelineOrchestrator, Depends(get_orchestrator)]
