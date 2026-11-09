"""Tracking table: persists pipeline runs and their task runs.

Single DynamoDB table, two item kinds sharing the partition key `run_id`:
    sk = "RUN"                      -> the pipeline run (status, timestamps...)
    sk = "TASK#<step>#<task>"       -> one item per task of the run
A GSI on (pipeline_name, started_at) lists the runs of a pipeline, newest first.

`InMemoryTrackingRepository` has the same interface for tests and local development.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Protocol

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import BotoCoreError, ClientError

from app.core.exceptions import ExternalServiceError, NotFoundError
from app.domain.pipeline import RunStatus

logger = logging.getLogger(__name__)

RUN_SK = "RUN"
TASK_SK_PREFIX = "TASK#"
PIPELINE_INDEX = "pipeline_name-started_at-index"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def task_sk(step_name: str, task_name: str) -> str:
    return f"{TASK_SK_PREFIX}{step_name}#{task_name}"


class TrackingRepository(Protocol):
    def create_run(self, run: dict[str, Any], tasks: list[dict[str, Any]]) -> None: ...
    def update_run(self, run_id: str, **fields: Any) -> None: ...
    def update_task(self, run_id: str, step_name: str, task_name: str, **fields: Any) -> None: ...
    def get_run(self, run_id: str) -> dict[str, Any]: ...
    def get_tasks(self, run_id: str) -> list[dict[str, Any]]: ...
    def list_runs(self, pipeline_name: str, limit: int = 20) -> list[dict[str, Any]]: ...
    def has_active_run(self, pipeline_name: str) -> bool: ...


class InMemoryTrackingRepository:
    """Dict-backed implementation (tests, local dev with TRACKING_BACKEND=memory)."""

    def __init__(self) -> None:
        self._items: dict[tuple[str, str], dict[str, Any]] = {}

    def create_run(self, run: dict[str, Any], tasks: list[dict[str, Any]]) -> None:
        self._items[(run["run_id"], RUN_SK)] = dict(run, sk=RUN_SK)
        for task in tasks:
            sk = task_sk(task["step_name"], task["task_name"])
            self._items[(run["run_id"], sk)] = dict(task, sk=sk)

    def update_run(self, run_id: str, **fields: Any) -> None:
        self._items[(run_id, RUN_SK)].update(fields)

    def update_task(self, run_id: str, step_name: str, task_name: str, **fields: Any) -> None:
        self._items[(run_id, task_sk(step_name, task_name))].update(fields)

    def get_run(self, run_id: str) -> dict[str, Any]:
        try:
            return dict(self._items[(run_id, RUN_SK)])
        except KeyError:
            raise NotFoundError(f"run '{run_id}' not found") from None

    def get_tasks(self, run_id: str) -> list[dict[str, Any]]:
        return [dict(item) for (rid, sk), item in self._items.items()
                if rid == run_id and sk.startswith(TASK_SK_PREFIX)]

    def list_runs(self, pipeline_name: str, limit: int = 20) -> list[dict[str, Any]]:
        runs = [dict(item) for (_, sk), item in self._items.items()
                if sk == RUN_SK and item["pipeline_name"] == pipeline_name]
        runs.sort(key=lambda run: run["started_at"], reverse=True)
        return runs[:limit]

    def has_active_run(self, pipeline_name: str) -> bool:
        return any(not RunStatus(run["status"]).is_terminal for run in self.list_runs(pipeline_name, limit=1000))


class DynamoDBTrackingRepository:
    def __init__(self, table_name: str, region: str, table: Any | None = None) -> None:
        self._table = table or boto3.resource("dynamodb", region_name=region).Table(table_name)

    def create_run(self, run: dict[str, Any], tasks: list[dict[str, Any]]) -> None:
        try:
            with self._table.batch_writer() as batch:
                batch.put_item(Item=dict(run, sk=RUN_SK))
                for task in tasks:
                    batch.put_item(Item=dict(task, sk=task_sk(task["step_name"], task["task_name"])))
        except (BotoCoreError, ClientError) as exc:
            raise _wrap("create_run", exc) from exc

    def update_run(self, run_id: str, **fields: Any) -> None:
        self._update({"run_id": run_id, "sk": RUN_SK}, fields)

    def update_task(self, run_id: str, step_name: str, task_name: str, **fields: Any) -> None:
        self._update({"run_id": run_id, "sk": task_sk(step_name, task_name)}, fields)

    def get_run(self, run_id: str) -> dict[str, Any]:
        try:
            item = self._table.get_item(Key={"run_id": run_id, "sk": RUN_SK}).get("Item")
        except (BotoCoreError, ClientError) as exc:
            raise _wrap("get_run", exc) from exc
        if item is None:
            raise NotFoundError(f"run '{run_id}' not found")
        return item

    def get_tasks(self, run_id: str) -> list[dict[str, Any]]:
        try:
            response = self._table.query(
                KeyConditionExpression=Key("run_id").eq(run_id) & Key("sk").begins_with(TASK_SK_PREFIX))
        except (BotoCoreError, ClientError) as exc:
            raise _wrap("get_tasks", exc) from exc
        return response.get("Items", [])

    def list_runs(self, pipeline_name: str, limit: int = 20) -> list[dict[str, Any]]:
        try:
            response = self._table.query(
                IndexName=PIPELINE_INDEX,
                KeyConditionExpression=Key("pipeline_name").eq(pipeline_name),
                ScanIndexForward=False,   # newest first
                Limit=limit,
            )
        except (BotoCoreError, ClientError) as exc:
            raise _wrap("list_runs", exc) from exc
        return response.get("Items", [])

    def has_active_run(self, pipeline_name: str) -> bool:
        # Only the most recent runs can still be active
        return any(not RunStatus(run["status"]).is_terminal for run in self.list_runs(pipeline_name, limit=10))

    def _update(self, key: dict[str, str], fields: dict[str, Any]) -> None:
        if not fields:
            return
        # Attribute names are aliased (#f0...) so reserved words like "status" are safe
        names = {f"#f{i}": name for i, name in enumerate(fields)}
        values = {f":v{i}": value for i, value in enumerate(fields.values())}
        expression = "SET " + ", ".join(f"{n} = {v}" for n, v in zip(names, values))
        try:
            self._table.update_item(
                Key=key,
                UpdateExpression=expression,
                ExpressionAttributeNames=names,
                ExpressionAttributeValues=values,
            )
        except (BotoCoreError, ClientError) as exc:
            raise _wrap("update", exc) from exc


def _wrap(operation: str, exc: Exception) -> ExternalServiceError:
    return ExternalServiceError(f"DynamoDB tracking {operation} failed: {exc}")
