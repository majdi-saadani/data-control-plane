"""FastAPI endpoint tests: services are replaced by fakes (no AWS/Databricks calls)."""

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_databricks_runner, get_event_sender
from app.clients.kinesis_client import PublishResult
from app.core.config import Settings, get_settings
from app.main import app
from app.schemas.databricks import RunJobResponse, RunStatusResponse
from app.services.event_sender import EventSenderService


class FakeKinesis:
    stream_name = "energy-sensor-events-test"

    def __init__(self) -> None:
        self.published: list[dict] = []

    def publish(self, events: list[dict]) -> PublishResult:
        self.published.extend(events)
        return PublishResult(sent=len(events), failed=0)


class FakeDatabricksRunner:
    def run_job(self, job_id: int, job_parameters: dict[str, str]) -> RunJobResponse:
        self.last_params = job_parameters
        return RunJobResponse(job_id=job_id, run_id=999)

    def get_run_status(self, run_id: int) -> RunStatusResponse:
        return RunStatusResponse(run_id=run_id, life_cycle_state="RUNNING")


@pytest.fixture
def kinesis() -> FakeKinesis:
    return FakeKinesis()


@pytest.fixture
def client(kinesis):
    app.dependency_overrides[get_event_sender] = lambda: EventSenderService(kinesis)
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_request_id_header_is_propagated(client):
    response = client.get("/health", headers={"X-Request-ID": "abc-123"})
    assert response.headers["X-Request-ID"] == "abc-123"


def test_send_events_publishes_to_kinesis(client, kinesis):
    response = client.post("/events/send", json={"count": 20, "seed": 42})

    assert response.status_code == 200
    body = response.json()
    assert body["generated"] == 20
    assert body["sent"] == 20
    assert body["duplicates"] >= 1
    assert body["negatives"] >= 1
    assert len(kinesis.published) == 20
    # Data contract expected by the Lambda
    assert {"event_id", "timestamp", "measurements"} <= kinesis.published[0].keys()


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
