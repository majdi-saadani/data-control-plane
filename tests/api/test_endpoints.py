"""FastAPI endpoint tests: services are replaced by fakes (no AWS/Databricks calls)."""

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_databricks_runner, get_event_sender, get_orchestrator, get_pipeline_registry
from app.clients.kinesis_client import PublishResult
from app.core.config import Settings, get_settings
from app.domain.pipeline import RunStatus
from app.main import app
from app.repositories.tracking_repository import InMemoryTrackingRepository
from app.schemas.databricks import RunJobResponse, RunStatusResponse
from app.services.event_sender import EventSenderService
from app.services.pipeline_orchestrator import PipelineOrchestrator
from app.services.pipeline_registry import PipelineRegistry
from app.services.task_executors import TaskOutcome


class FakeKinesis:
    stream_name = "energy-sensor-events-test"

    def __init__(self) -> None:
        self.published: list[dict] = []

    def publish(self, records: list[dict]) -> PublishResult:
        self.published.extend(records)
        return PublishResult(sent=len(records), failed=0)


class FakeDatabricksRunner:
    def run_job(self, job_id: int, job_parameters: dict[str, str]) -> RunJobResponse:
        self.last_params = job_parameters
        return RunJobResponse(job_id=job_id, run_id=999)

    def get_run_status(self, run_id: int) -> RunStatusResponse:
        return RunStatusResponse(run_id=run_id, life_cycle_state="RUNNING")


class AlwaysSucceeds:
    def run(self, task, context, on_started) -> TaskOutcome:
        return TaskOutcome(status=RunStatus.SUCCESS, external_ref="ref-1")


@pytest.fixture
def kinesis() -> FakeKinesis:
    return FakeKinesis()


@pytest.fixture
def orchestrator() -> PipelineOrchestrator:
    registry = PipelineRegistry.from_yaml("config/pipelines.yaml")
    executors = {"lambda": AlwaysSucceeds(), "databricks_job": AlwaysSucceeds()}
    return PipelineOrchestrator(registry, InMemoryTrackingRepository(), executors)


@pytest.fixture
def client(kinesis, orchestrator):
    app.dependency_overrides[get_event_sender] = lambda: EventSenderService(kinesis)
    app.dependency_overrides[get_pipeline_registry] = lambda: PipelineRegistry.from_yaml("config/pipelines.yaml")
    app.dependency_overrides[get_orchestrator] = lambda: orchestrator
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_request_id_header_is_propagated(client):
    response = client.get("/health", headers={"X-Request-ID": "abc-123"})
    assert response.headers["X-Request-ID"] == "abc-123"


def test_send_events_publishes_envelopes_to_kinesis(client, kinesis):
    response = client.post("/events/send", json={"count": 20, "seed": 42}, headers={"X-Request-ID": "call-42"})

    assert response.status_code == 200
    body = response.json()
    assert body["generated"] == 20
    assert body["sent"] == 20
    assert body["call_id"] == "call-42"
    assert body["duplicates"] >= 1
    assert body["negatives"] >= 1
    assert len(kinesis.published) == 20
    # Envelope + data contract expected by the consumer Lambda
    envelope = kinesis.published[0]
    assert envelope["call_id"] == "call-42"
    assert envelope["type"] == "energy.measurement"
    assert envelope["emitted_at"].endswith("Z")
    assert {"event_id", "sensor_id", "timestamp", "measurements"} <= envelope["data"].keys()


def test_send_events_dry_run_does_not_publish(client, kinesis):
    response = client.post("/events/send", json={"count": 10, "dry_run": True})

    assert response.status_code == 200
    assert response.json()["sent"] == 0
    assert kinesis.published == []


def test_send_events_validates_count(client):
    assert client.post("/events/send", json={"count": 0}).status_code == 422


def test_run_databricks_job(client):
    runner = FakeDatabricksRunner()
    app.dependency_overrides[get_databricks_runner] = lambda: runner

    response = client.post("/databricks/jobs/123/run", json={"job_parameters": {"date": "2026-11-03"}})

    assert response.status_code == 202
    assert response.json() == {"job_id": 123, "run_id": 999}
    assert runner.last_params == {"date": "2026-11-03"}


def test_get_databricks_run_status(client):
    app.dependency_overrides[get_databricks_runner] = lambda: FakeDatabricksRunner()

    response = client.get("/databricks/runs/999")

    assert response.status_code == 200
    assert response.json()["life_cycle_state"] == "RUNNING"


def test_databricks_not_configured_returns_503(client):
    app.dependency_overrides[get_settings] = lambda: Settings(databricks_host=None, databricks_token=None)

    response = client.post("/databricks/jobs/123/run")

    assert response.status_code == 503


def test_list_pipelines_from_config(client):
    response = client.get("/pipelines")

    assert response.status_code == 200
    names = {pipeline["name"] for pipeline in response.json()}
    assert "energy-medallion" in names
    medallion = next(p for p in response.json() if p["name"] == "energy-medallion")
    assert [step["name"] for step in medallion["steps"]] == ["generate", "bronze", "silver", "gold"]


def test_unknown_pipeline_returns_404(client):
    assert client.get("/pipelines/nope").status_code == 404
    assert client.post("/pipelines/nope/run").status_code == 404


def test_run_pipeline_then_follow_it(client):
    started = client.post("/pipelines/generate-only/run", headers={"X-Request-ID": "call-7"})
    assert started.status_code == 202
    assert started.json()["call_id"] == "call-7"
    run_id = started.json()["run_id"]

    # TestClient runs background tasks before returning: the run is already finished
    run = client.get(f"/runs/{run_id}")
    assert run.status_code == 200
    assert run.json()["status"] == "SUCCESS"
    assert run.json()["tasks"][0]["status"] == "SUCCESS"
    assert run.json()["tasks"][0]["external_ref"] == "ref-1"

    listed = client.get("/pipelines/generate-only/runs")
    assert [r["run_id"] for r in listed.json()] == [run_id]


def test_unknown_run_returns_404(client):
    assert client.get("/runs/does-not-exist").status_code == 404
