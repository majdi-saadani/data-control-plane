"""Task executors: one class per task type, each runs a task to completion.

An executor blocks until the task reaches a terminal state (it polls when the
backend is asynchronous, as Databricks is). The orchestrator runs executors in
threads, so blocking here is what makes parallel steps possible.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from app.clients.databricks_client import DatabricksClient
from app.clients.lambda_client import LambdaClient
from app.core.exceptions import AppError
from app.domain.pipeline import DatabricksJobTask, LambdaTask, RunStatus

logger = logging.getLogger(__name__)

# Called as soon as the external run is known, so the tracking table shows it while the task runs
OnStarted = Callable[[dict[str, Any]], None]

DATABRICKS_TERMINAL_STATES = {"TERMINATED", "SKIPPED", "INTERNAL_ERROR"}


@dataclass(frozen=True, slots=True)
class TaskContext:
    run_id: str
    call_id: str
    timeout_s: float


@dataclass(slots=True)
class TaskOutcome:
    status: RunStatus
    message: str | None = None
    external_ref: str | None = None         # databricks run_id, lambda request id...
    run_page_url: str | None = None
    result: dict[str, Any] = field(default_factory=dict)


class TaskExecutor(Protocol):
    def run(self, task: Any, context: TaskContext, on_started: OnStarted) -> TaskOutcome: ...


class DatabricksJobExecutor:
    """run-now, then poll runs/get until the run terminates (or the timeout hits)."""

    def __init__(self, client: DatabricksClient, poll_interval_s: float,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        self._client = client
        self._poll_interval_s = poll_interval_s
        self._sleep = sleep

    def run(self, task: DatabricksJobTask, context: TaskContext, on_started: OnStarted) -> TaskOutcome:
        job_id = task.job_id if task.job_id is not None else self._client.find_job_id(task.job_name)
        run_id = int(self._client.run_now(job_id, task.parameters)["run_id"])
        on_started({"external_ref": str(run_id), "result": json.dumps({"job_id": job_id})})

        deadline = time.monotonic() + context.timeout_s
        while True:
            run = self._client.get_run(run_id)
            state = run.get("state", {})
            if state.get("life_cycle_state") in DATABRICKS_TERMINAL_STATES:
                success = state.get("result_state") == "SUCCESS"
                return TaskOutcome(
                    status=RunStatus.SUCCESS if success else RunStatus.FAILED,
                    message=state.get("state_message") or state.get("result_state"),
                    external_ref=str(run_id),
                    run_page_url=run.get("run_page_url"),
                    result={"job_id": job_id, "result_state": state.get("result_state")},
                )
            if time.monotonic() >= deadline:
                logger.warning("Databricks run %s timed out after %.0fs, cancelling", run_id, context.timeout_s)
                self._client.cancel_run(run_id)
                return TaskOutcome(status=RunStatus.TIMEOUT, message="timeout reached, run cancelled",
                                   external_ref=str(run_id), run_page_url=run.get("run_page_url"))
            self._sleep(self._poll_interval_s)


class LambdaExecutor:
    """Synchronous invoke: the Lambda's own timeout bounds the task."""

    def __init__(self, client: LambdaClient) -> None:
        self._client = client

    def run(self, task: LambdaTask, context: TaskContext, on_started: OnStarted) -> TaskOutcome:
        payload = {**task.payload, "run_id": context.run_id, "call_id": context.call_id}
        on_started({"result": json.dumps({"function_name": task.function_name})})
        invocation = self._client.invoke(task.function_name, payload)
        result = invocation.payload if isinstance(invocation.payload, dict) else {"payload": invocation.payload}
        if invocation.succeeded:
            return TaskOutcome(status=RunStatus.SUCCESS, external_ref=invocation.request_id, result=result)
        message = f"{invocation.function_error}: {result.get('errorMessage', result)}"
        return TaskOutcome(status=RunStatus.FAILED, message=message,
                           external_ref=invocation.request_id, result=result)


def run_safely(executor: TaskExecutor, task: Any, context: TaskContext, on_started: OnStarted) -> TaskOutcome:
    """Never let an executor exception escape: it becomes a FAILED outcome."""
    try:
        return executor.run(task, context, on_started)
    except AppError as exc:
        return TaskOutcome(status=RunStatus.FAILED, message=exc.message)
    except Exception as exc:  # noqa: BLE001 - last resort, the run must still be marked FAILED
        logger.exception("Unexpected error in task '%s'", task.name)
        return TaskOutcome(status=RunStatus.FAILED, message=f"{type(exc).__name__}: {exc}")
