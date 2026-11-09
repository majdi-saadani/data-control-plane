"""Event generator Lambda: produces synthetic energy events and publishes them to Kinesis.

Invoked by the control plane (pipeline task of type `lambda`) or manually:
    {"count": 200, "seed": 42, "call_id": "<optional>"}

Each record is wrapped in the envelope {call_id, type, emitted_at, data}, the
same format as POST /events/send. When no call_id is given, the Lambda's own
aws_request_id is used.

Self-contained on purpose: Terraform packages this single file, so only the
stdlib and the runtime's boto3 are available. The generation logic mirrors
app/domain/event_generator.py (same sensors, same ~15% duplicates / negatives).
"""

import json
import os
import random
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import boto3

EVENT_TYPE = "energy.measurement"
MAX_RECORDS_PER_CALL = 500
DUPLICATE_RATIO = 0.15
NEGATIVE_RATIO = 0.15
DEFAULT_COUNT = 100
MAX_COUNT = 5000

SITE_BY_SENSOR = {
    "SENS-FR-IDF-0001": "SITE-PARIS-EST",
    "SENS-FR-IDF-0002": "SITE-PARIS-EST",
    "SENS-FR-IDF-0003": "SITE-CRETEIL",
    "SENS-FR-HDF-0010": "SITE-LILLE",
    "SENS-FR-PAC-0021": "SITE-MARSEILLE",
}
SENSOR_IDS = tuple(SITE_BY_SENSOR)

kinesis = None


def _get_kinesis():
    global kinesis
    if kinesis is None:
        kinesis = boto3.client("kinesis")
    return kinesis


def _iso(at: datetime) -> str:
    return at.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _base_load_kw(at: datetime) -> float:
    hour = at.hour + at.minute / 60
    return 12.0 + 30 * pow(2.718, -((hour - 12) ** 2) / 8) + 45 * pow(2.718, -((hour - 19) ** 2) / 6)


def make_event(rng: random.Random, at: datetime, negative: bool = False) -> dict[str, Any]:
    sensor_id = rng.choice(SENSOR_IDS)
    power_kw = round(_base_load_kw(at) * rng.uniform(0.85, 1.15), 2)
    if negative:
        power_kw = -abs(power_kw)
    voltage_v = round(rng.gauss(230.0, 2.5), 1)
    return {
        "event_id": str(uuid.UUID(int=rng.getrandbits(128), version=4)),
        "sensor_id": sensor_id,
        "site_id": SITE_BY_SENSOR[sensor_id],
        "timestamp": _iso(at),
        "measurements": {
            "power_kw": power_kw,
            "energy_kwh": round(rng.uniform(1000, 5000), 2),
            "voltage_v": voltage_v,
            "current_a": round(abs(power_kw) * 1000 / max(voltage_v, 1.0), 1),
            "frequency_hz": round(rng.gauss(50.0, 0.05), 3),
        },
        "temperature_c": round(rng.uniform(25.0, 55.0), 1),
        "status": "FAULT" if negative else "OK",
    }


def generate_events(count: int, seed: int | None) -> list[dict[str, Any]]:
    rng = random.Random(seed)
    now = datetime.now(timezone.utc)
    n_duplicates = max(1, int(count * DUPLICATE_RATIO))
    n_originals = count - n_duplicates
    negative_slots = set(rng.sample(range(n_originals), k=min(max(1, int(count * NEGATIVE_RATIO)), n_originals)))

    events = [make_event(rng, now - timedelta(seconds=rng.randint(0, 3600)), negative=i in negative_slots)
              for i in range(n_originals)]
    events.extend(rng.choices(events, k=n_duplicates))   # exact duplicates (at-least-once delivery)
    rng.shuffle(events)
    return events


def wrap(data: dict[str, Any], call_id: str) -> dict[str, Any]:
    return {"call_id": call_id, "type": EVENT_TYPE, "emitted_at": _iso(datetime.now(timezone.utc)), "data": data}


def publish(stream_name: str, records: list[dict[str, Any]]) -> tuple[int, int]:
    sent = failed = 0
    for start in range(0, len(records), MAX_RECORDS_PER_CALL):
        chunk = records[start:start + MAX_RECORDS_PER_CALL]
        response = _get_kinesis().put_records(
            StreamName=stream_name,
            Records=[{"Data": json.dumps(r).encode("utf-8"), "PartitionKey": r["data"]["sensor_id"]} for r in chunk],
        )
        failed += response["FailedRecordCount"]
        sent += len(chunk) - response["FailedRecordCount"]
    return sent, failed


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    count = min(int(event.get("count", DEFAULT_COUNT)), MAX_COUNT)
    if count < 1:
        raise ValueError("count must be >= 1")
    seed = event.get("seed")
    call_id = event.get("call_id") or getattr(context, "aws_request_id", str(uuid.uuid4()))
    stream_name = os.environ["STREAM_NAME"]

    events = generate_events(count, seed)
    records = [wrap(e, call_id) for e in events]
    sent, failed = publish(stream_name, records)

    summary = {
        "stream_name": stream_name,
        "call_id": call_id,
        "generated": len(events),
        "duplicates": len(events) - len({e["event_id"] for e in events}),
        "negatives": sum(1 for e in events if e["measurements"]["power_kw"] < 0),
        "sent": sent,
        "failed": failed,
    }
    print(json.dumps(summary))
    if failed:
        raise RuntimeError(f"{failed} record(s) failed to publish to {stream_name}")
    return summary
