"""Unit tests for the pipeline orchestrator: fake executors, in-memory tracking, no AWS/Databricks."""

import threading

import pytest

from app.core.exceptions import ConflictError, ServiceNotConfiguredError
from app.domain.pipeline import Pipeline, RunStatus
from app.repositories.tracking_repository import InMemoryTrackingRepository
from app.services.pipeline_orchestrator import PipelineOrchestrator
from app.services.pipeline_registry import PipelineRegistry
from app.services.task_executors import TaskOutcome


class ScriptedExecutor:
    """Returns the outcome scripted per task name; records the order of execution."""

    def __init__(self, outcomes: dict[str, RunStatus] | None = None) -> None:
        self.outcomes = outcomes or {}
        self.calls: list[str] = []
        self.active = 0
        self.max_active = 0
        self._lock = threading.Lock()
        self._barrier: threading.Barrier | None = None
        self._parallel_tasks: set[str] = set()

    def expect_parallel(self, *task_names: str) -> None:
        # These tasks must all be running at the same time, otherwise the barrier times out
        self._parallel_tasks = set(task_names)
        self._barrier = threading.Barrier(len(task_names), timeout=2)

    def run(self, task, context, on_started) -> TaskOutcome:
        with self._lock:
            self.calls.append(task.name)
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        on_started({"external_ref": f"ref-{task.name}"})
        if self._barrier and task.name in self._parallel_tasks:
            self._barrier.wait()
        with self._lock:
            self.active -= 1
        status = self.outcomes.get(task.name, RunStatus.SUCCESS)
        return TaskOutcome(status=status, message=None if status is RunStatus.SUCCESS else "boom",
                           external_ref=f"ref-{task.name}", result={"ok": status is RunStatus.SUCCESS})


def make_registry() -> PipelineRegistry:
    pipeline = Pipeline.model_validate({
        "name": "demo",
        "steps": [
            {"name": "generate", "tasks": [{"name": "gen", "type": "lambda", "function_name": "fn"}]},
            {"name": "bronze", "mode": "parallel", "tasks": [
                {"name": "b1", "type": "databricks_job", "job_name": "job-b1"},
                {"name": "b2", "type": "databricks_job", "job_id": 42},
            ]},
            {"name": "gold", "mode": "sequential", "tasks": [
                {"name": "g1", "type": "databricks_job", "job_name": "job-g1"},
                {"name": "g2", "type": "databricks_job", "job_name": "job-g2"},
            ]},
        ],
    })
    return PipelineRegistry({"demo": pipeline})


@pytest.fixture
def repo() -> InMemoryTrackingRepository:
    return InMemoryTrackingRepository()


def build(repo, executor) -> PipelineOrchestrator:
    return PipelineOrchestrator(make_registry(), repo, {"lambda": executor, "databricks_job": executor})


def statuses(orchestrator: PipelineOrchestrator, run_id: str) -> dict[str, str]:
    return {f"{t['step_name']}/{t['task_name']}": t["status"] for t in orchestrator.get_run(run_id)["tasks"]}


def test_successful_run_executes_every_step_in_order(repo):
    executor = ScriptedExecutor()
    orchestrator = build(repo, executor)

    run = orchestrator.start_run("demo", call_id="call-1")
    assert run["status"] == "PENDING"
    assert len(repo.get_tasks(run["run_id"])) == 5

    assert orchestrator.execute_run(run["run_id"], "demo", "call-1") is RunStatus.SUCCESS

    result = orchestrator.get_run(run["run_id"])
    assert result["status"] == "SUCCESS"
    assert result["finished_at"] is not None
    assert result["current_step"] == "gold"
    assert set(statuses(orchestrator, run["run_id"]).values()) == {"SUCCESS"}
    # Steps in order; inside the sequential gold step, g1 before g2
    assert executor.calls[0] == "gen"
    assert set(executor.calls[1:3]) == {"b1", "b2"}
    assert executor.calls[3:] == ["g1", "g2"]
    # external_ref written by on_started() and kept at the end
    tasks = {t["task_name"]: t for t in result["tasks"]}
    assert tasks["b2"]["external_ref"] == "ref-b2"
    assert tasks["b2"]["result"] == '{"ok": true}'


def test_parallel_step_runs_tasks_concurrently(repo):
    executor = ScriptedExecutor()
    executor.expect_parallel("b1", "b2")   # b1 and b2 must overlap, otherwise the barrier raises
    orchestrator = build(repo, executor)

    run = orchestrator.start_run("demo", call_id="c")
    assert orchestrator.execute_run(run["run_id"], "demo", "c") is RunStatus.SUCCESS
    assert executor.max_active == 2


def test_failed_step_skips_the_following_steps(repo):
    executor = ScriptedExecutor({"b1": RunStatus.FAILED})
    orchestrator = build(repo, executor)

    run = orchestrator.start_run("demo", call_id="c")
    assert orchestrator.execute_run(run["run_id"], "demo", "c") is RunStatus.FAILED

    result = orchestrator.get_run(run["run_id"])
    assert result["status"] == "FAILED"
    assert "bronze/b1" in result["error"]
    assert statuses(orchestrator, run["run_id"]) == {
        "generate/gen": "SUCCESS",
        "bronze/b1": "FAILED",
        "bronze/b2": "SUCCESS",      # parallel sibling still completes
        "gold/g1": "SKIPPED",
        "gold/g2": "SKIPPED",
    }
    assert "g1" not in executor.calls


def test_sequential_step_stops_at_first_failure(repo):
    executor = ScriptedExecutor({"g1": RunStatus.TIMEOUT})
    orchestrator = build(repo, executor)

    run = orchestrator.start_run("demo", call_id="c")
    orchestrator.execute_run(run["run_id"], "demo", "c")

    assert statuses(orchestrator, run["run_id"])["gold/g1"] == "TIMEOUT"
    assert statuses(orchestrator, run["run_id"])["gold/g2"] == "SKIPPED"
    assert "g2" not in executor.calls


def test_executor_exception_marks_task_failed_not_run_stuck(repo):
    class Exploding:
        def run(self, task, context, on_started):
            raise RuntimeError("network down")

    orchestrator = build(repo, Exploding())
    run = orchestrator.start_run("demo", call_id="c")
    assert orchestrator.execute_run(run["run_id"], "demo", "c") is RunStatus.FAILED
    task = orchestrator.get_run(run["run_id"])["tasks"][0]
    assert task["status"] == "FAILED"
    assert "network down" in task["error"]


def test_only_one_active_run_per_pipeline(repo):
    orchestrator = build(repo, ScriptedExecutor())
    orchestrator.start_run("demo", call_id="c")
    with pytest.raises(ConflictError):
        orchestrator.start_run("demo", call_id="c")


def test_missing_executor_is_a_configuration_problem(repo):
    orchestrator = PipelineOrchestrator(make_registry(), repo, {"lambda": ScriptedExecutor()})
    with pytest.raises(ServiceNotConfiguredError, match="databricks_job"):
        orchestrator.start_run("demo", call_id="c")
