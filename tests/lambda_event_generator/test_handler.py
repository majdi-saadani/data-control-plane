"""Unit tests for the event generator Lambda (Kinesis stubbed)."""

import json

import pytest

from lambda_event_generator import handler


class FakeKinesis:
    def __init__(self) -> None:
        self.records: list[dict] = []

    def put_records(self, StreamName, Records):
        self.records.extend(Records)
        return {"FailedRecordCount": 0}


class FakeContext:
    aws_request_id = "aws-req-1"


@pytest.fixture
def kinesis(monkeypatch):
    fake = FakeKinesis()
    monkeypatch.setattr(handler, "kinesis", fake)
    monkeypatch.setenv("STREAM_NAME", "energy-sensor-events-test")
    return fake


def test_generates_envelopes_with_pipeline_call_id(kinesis):
    summary = handler.lambda_handler({"count": 40, "seed": 1, "call_id": "run-call"}, FakeContext())

    assert summary["generated"] == summary["sent"] == 40
    assert summary["duplicates"] >= 1 and summary["negatives"] >= 1
    assert len(kinesis.records) == 40
    envelope = json.loads(kinesis.records[0]["Data"])
    assert envelope["call_id"] == "run-call"
    assert envelope["type"] == "energy.measurement"
    assert kinesis.records[0]["PartitionKey"] == envelope["data"]["sensor_id"]
    assert {"event_id", "timestamp", "measurements"} <= envelope["data"].keys()


def test_falls_back_to_aws_request_id(kinesis):
    summary = handler.lambda_handler({"count": 5}, FakeContext())
    assert summary["call_id"] == "aws-req-1"
