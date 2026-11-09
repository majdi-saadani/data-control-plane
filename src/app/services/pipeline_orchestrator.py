"""Pipeline orchestrator: runs steps in order, tasks in parallel or sequence, tracks everything.

Lifecycle of a run:
    start_run()    -> validates, writes the RUN item + one PENDING item per task, returns immediately
    execute_run()  -> runs in a background thread: step by step, updates the tracking table live
A step runs only if the previous step succeeded; otherwise its tasks are marked SKIPPED.
"""

from __future__ import annotations

import json
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from app.core.exceptions import ConflictError, ServiceNotConfiguredError
from app.domain.pipeline import ExecutionMode, Pipeline, RunStatus, Step
from app.repositories.tracking_repository import TrackingRepository, utc_now
from app.services.pipeline_registry import PipelineRegistry
from app.services.task_executors import OnStarted, TaskContext, TaskExecutor, TaskOutcome, run_safely

logger = logging.getLogger(__name__)


class PipelineOrchestrator:
    def __init__(self, registry: PipelineRegistry, repository: TrackingRepository,
                 executors: dict[str, TaskExecutor], default_task_timeout_min: int = 60) -> None:
        self._registry = registry
        self._repository = repository
        self._executors = executors            # task type -> executor
        self._default_timeout_s = default_task_timeout_min * 60

    # ------------------------------------------------------------------ public API

    def start_run(self, pipeline_name: str, call_id: str) -> dict[str, Any]:
        """Create the run in the tracking table (status PENDING). Execution happens in execute_run."""
        pipeline = self._registry.get(pipeline_name)
        self._check_executors(pipeline)
        if self._repository.has_active_run(pipeline_name):
            raise ConflictError(f"pipeline '{pipeline_name}' already has an active run")

        run_id = str(uuid.uuid4())
        now = utc_now()
        run = {
            "run_id": run_id,
            "pipeline_name": pipeline_name,
            "status": RunStatus.PENDING.value,
            "call_id": call_id,
            "started_at": now,
            "finished_at": None,
            "current_step": None,
            "error": None,
        }
        tasks = [
            {
                "run_id": run_id,
                "step_name": step.name,
                "task_name": task.name,
                "task_type": task.type,
                "status": RunStatus.PENDING.value,
                "external_ref": None,
                "run_page_url": None,
                "started_at": None,
                "finished_at": None,
                "error": None,
                "result": None,
            }
            for step in pipeline.steps
            for task in step.tasks
        ]
        self._repository.create_run(run, tasks)
        logger.info("Run %s created for pipeline '%s' (call_id=%s)", run_id, pipeline_name, call_id)
        return run

    def execute_run(self, run_id: str, pipeline_name: str, call_id: str) -> RunStatus:
        """Blocking: runs every step. Designed to be scheduled as a background task."""
        pipeline = self._registry.get(pipeline_name)
        self._repository.update_run(run_id, status=RunStatus.RUNNING.value)
        final_status = RunStatus.SUCCESS
        error: str | None = None

        try:
            for step in pipeline.steps:
                if final_status is not RunStatus.SUCCESS:
                    self._skip_step(run_id, step)
                    continue
                self._repository.update_run(run_id, current_step=step.name)
                outcomes = self._run_step(run_id, call_id, step)
                failed = [(name, outcome) for name, outcome in outcomes.items() if outcome.status is not RunStatus.SUCCESS]
                if failed:
                    final_status = RunStatus.FAILED
                    error = "; ".join(f"{step.name}/{name}: {outcome.status} {outcome.message or ''}".strip()
                                      for name, outcome in failed)
        except Exception as exc:  # noqa: BLE001 - the run must never stay RUNNING
            logger.exception("Run %s crashed", run_id)
            final_status, error = RunStatus.FAILED, f"{type(exc).__name__}: {exc}"

        self._repository.update_run(run_id, status=final_status.value, finished_at=utc_now(), error=error)
        logger.info("Run %s finished: %s", run_id, final_status)
        return final_status

    def get_run(self, run_id: str) -> dict[str, Any]:
        run = self._repository.get_run(run_id)
        run["tasks"] = sorted(self._repository.get_tasks(run_id), key=lambda t: self._task_order(run["pipeline_name"], t))
        return run

    def list_runs(self, pipeline_name: str, limit: int = 20) -> list[dict[str, Any]]:
        self._registry.get(pipeline_name)   # 404 if unknown
        return self._repository.list_runs(pipeline_name, limit)

    # ------------------------------------------------------------------ internals

    def _check_executors(self, pipeline: Pipeline) -> None:
        missing = {task.type for step in pipeline.steps for task in step.tasks} - self._executors.keys()
        if missing:
            raise ServiceNotConfiguredError(f"no executor configured for task type(s): {', '.join(sorted(missing))}")

    def _run_step(self, run_id: str, call_id: str, step: Step) -> dict[str, TaskOutcome]:
        logger.info("Run %s: step '%s' (%s, %d task(s))", run_id, step.name, step.mode, len(step.tasks))
        if step.mode is ExecutionMode.PARALLEL:
            with ThreadPoolExecutor(max_workers=len(step.tasks), thread_name_prefix=f"step-{step.name}") as pool:
                futures = {task.name: pool.submit(self._run_task, run_id, call_id, step.name, task) for task in step.tasks}
                return {name: future.result() for name, future in futures.items()}

        outcomes: dict[str, TaskOutcome] = {}
        for task in step.tasks:
            outcomes[task.name] = self._run_task(run_id, call_id, step.name, task)
            if outcomes[task.name].status is not RunStatus.SUCCESS:
                # Sequential: stop at the first failure, the rest of the step is skipped
                for remaining in step.tasks[len(outcomes):]:
                    self._repository.update_task(run_id, step.name, remaining.name, status=RunStatus.SKIPPED.value)
                break
        return outcomes

    def _run_task(self, run_id: str, call_id: str, step_name: str, task: Any) -> TaskOutcome:
        self._repository.update_task(run_id, step_name, task.name, status=RunStatus.RUNNING.value, started_at=utc_now())
        timeout_s = (task.timeout_minutes * 60) if task.timeout_minutes else self._default_timeout_s
        context = TaskContext(run_id=run_id, call_id=call_id, timeout_s=timeout_s)

        on_started: OnStarted = lambda fields: self._repository.update_task(run_id, step_name, task.name, **fields)
        outcome = run_safely(self._executors[task.type], task, context, on_started)

        self._repository.update_task(
            run_id, step_name, task.name,
            status=outcome.status.value,
            finished_at=utc_now(),
            error=outcome.message if outcome.status is not RunStatus.SUCCESS else None,
            external_ref=outcome.external_ref,
            run_page_url=outcome.run_page_url,
            result=json.dumps(outcome.result) if outcome.result else None,
        )
        logger.info("Run %s: task '%s/%s' -> %s", run_id, step_name, task.name, outcome.status)
        return outcome

    def _skip_step(self, run_id: str, step: Step) -> None:
        for task in step.tasks:
            self._repository.update_task(run_id, step.name, task.name, status=RunStatus.SKIPPED.value)

    def _task_order(self, pipeline_name: str, task_item: dict[str, Any]) -> tuple[int, int]:
        """Sort task items in pipeline definition order."""
        pipeline = self._registry.get(pipeline_name)
        for s_idx, step in enumerate(pipeline.steps):
            if step.name == task_item["step_name"]:
                for t_idx, task in enumerate(step.tasks):
                    if task.name == task_item["task_name"]:
                        return (s_idx, t_idx)
        return (len(pipeline.steps), 0)
