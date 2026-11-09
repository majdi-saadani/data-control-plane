"""Unit tests for the task executors with fake Databricks / Lambda clients."""

import io
import json

from app.clients.databricks_client import DatabricksClient
from app.clients.lambda_client import LambdaClient
from app.domain.pipeline import DatabricksJobTask, LambdaTask, RunStatus
from app.services.task_executors import DatabricksJobExecutor, LambdaExecutor, TaskContext

CONTEXT = TaskContext(run_id="run-1", call_id="call-1", timeout_s=3600)


class FakeDatabricksHttp:
    """Just enough of httpx.Client for DatabricksClient: jobs/list, run-now, runs/get."""

    def __init__(self, states: list[dict]) -> None:
        self.states = states
        self.requests: list[tuple[str, str, dict]] = []

    def request(self, method, path, **kwargs):
        self.requests.append((method, path, kwargs))
        if path.endswith("/jobs/list"):
            body = {"jobs": [{"job_id": 77, "settings": {"name": kwargs["params"]["name"]}}]}
        elif path.endswith("/run-now"):
            body = {"run_id": 5001}
        elif path.endswith("/runs/get"):
            body = {"state": self.states.pop(0), "run_page_url": "https://dbx/run/5001"}
        else:
            raise AssertionError(path)
        return FakeResponse(body)


class FakeResponse:
    def __init__(self, body):
        self.content = json.dumps(body).encode()
        self._body = body

    def raise_for_status(self):
        return None

    def json(self):
        return self._body


def test_databricks_executor_resolves_name_polls_until_terminated():
    http = FakeDatabricksHttp(states=[
        {"life_cycle_state": "PENDING"},
        {"life_cycle_state": "RUNNING"},
        {"life_cycle_state": "TERMINATED", "result_state": "SUCCESS"},
    ])
    sleeps: list[float] = []
    executor = DatabricksJobExecutor(DatabricksClient("https://dbx", "tok", http_client=http),
                                     poll_interval_s=15, sleep=sleeps.append)
    started: list[dict] = []

    task = DatabricksJobTask(name="ingest", job_name="energy_bronze", parameters={"date": "2026-11-09"})
    outcome = executor.run(task, CONTEXT, started.append)

    assert outcome.status is RunStatus.SUCCESS
    assert outcome.external_ref == "5001"
    assert outcome.run_page_url == "https://dbx/run/5001"
    assert started[0]["external_ref"] == "5001"
    assert sleeps == [15, 15]
    run_now = next(kw for m, p, kw in http.requests if p.endswith("/run-now"))
    assert run_now["json"] == {"job_id": 77, "job_parameters": {"date": "2026-11-09"}}


def test_databricks_executor_reports_failed_runs():
    http = FakeDatabricksHttp(states=[{"life_cycle_state": "TERMINATED", "result_state": "FAILED",
                                       "state_message": "Task failed"}])
    executor = DatabricksJobExecutor(DatabricksClient("https://dbx", "tok", http_client=http),
                                     poll_interval_s=0, sleep=lambda s: None)

    outcome = executor.run(DatabricksJobTask(name="x", job_id=77), CONTEXT, lambda f: None)

    assert outcome.status is RunStatus.FAILED
    assert outcome.message == "Task failed"


class FakeLambdaBoto:
    def __init__(self, payload: dict, function_error: str | None = None) -> None:
        self.payload, self.function_error, self.last_call = payload, function_error, None

    def invoke(self, **kwargs):
        self.last_call = kwargs
        response = {"StatusCode": 200, "Payload": io.BytesIO(json.dumps(self.payload).encode()),
                    "ResponseMetadata": {"RequestId": "req-1"}}
        if self.function_error:
            response["FunctionError"] = self.function_error
        return response


def test_lambda_executor_passes_run_and_call_id():
    boto = FakeLambdaBoto({"generated": 50})
    executor = LambdaExecutor(LambdaClient(region="eu-west-1", boto_client=boto))

    outcome = executor.run(LambdaTask(name="gen", function_name="fn", payload={"count": 50}), CONTEXT, lambda f: None)

    assert outcome.status is RunStatus.SUCCESS
    assert outcome.result == {"generated": 50}
    assert json.loads(boto.last_call["Payload"]) == {"count": 50, "run_id": "run-1", "call_id": "call-1"}


def test_lambda_executor_reports_function_errors():
    boto = FakeLambdaBoto({"errorMessage": "count must be >= 1"}, function_error="Unhandled")
    executor = LambdaExecutor(LambdaClient(region="eu-west-1", boto_client=boto))

    outcome = executor.run(LambdaTask(name="gen", function_name="fn"), CONTEXT, lambda f: None)

    assert outcome.status is RunStatus.FAILED
    assert "count must be >= 1" in outcome.message
