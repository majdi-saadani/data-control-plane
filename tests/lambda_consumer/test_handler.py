"""Unit tests for the Kinesis consumer handler."""

import base64
import json

import pytest

from lambda_consumer import handler
from lambda_consumer.handler import lambda_handler


@pytest.fixture(autouse=True)
def stub_dynamodb(monkeypatch):
    """Replace the DynamoDB write with a stub: no AWS call in unit tests."""
    monkeypatch.setattr(handler, "write_to_dynamodb", lambda events: len(events))


def make_kinesis_record(energy_event: dict) -> dict:
    data = base64.b64encode(json.dumps(energy_event).encode("utf-8")).decode("utf-8")
    return {"kinesis": {"data": data, "partitionKey": energy_event.get("sensor_id", "unknown")}}


def make_event(event_id: str, power_kw: float) -> dict:
    return {
        "event_id": event_id,
        "sensor_id": "SENS-TEST-0001",
        "timestamp": "2026-07-06T10:00:00.000Z",
        "measurements": {"power_kw": power_kw},
    }


def test_dedup_filter_and_reject():
    malformed = {"kinesis": {"data": base64.b64encode(b'{"oops": true}').decode("utf-8")}}

    batch = {
        "Records": [
            make_kinesis_record(make_event("aaa", 42.5)),   # valid
            make_kinesis_record(make_event("bbb", -10.0)),  # negative -> filtered
            make_kinesis_record(make_event("aaa", 42.5)),   # duplicate -> dropped
            make_kinesis_record(make_event("ccc", 33.1)),   # valid
            malformed,                                       # invalid schema -> rejected
        ]
    }

    result = lambda_handler(batch, context=None)

    assert result == {
        "received": 5,
        "duplicates": 1,
        "negatives": 1,
        "rejected": 1,
        "written": 2,
    }


def test_empty_batch():
    result = lambda_handler({"Records": []}, context=None)
    assert result["written"] == 0
    assert result["rejected"] == 0