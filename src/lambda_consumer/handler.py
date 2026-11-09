"""Kinesis consumer: unwrap + dedup + filter + write to DynamoDB."""

import base64
import json
import os
from decimal import Decimal
from typing import Any

import boto3

# Lazily initialized (cold start), reused across invocations
dynamodb = None
table = None


def _get_table():
    """Lazy init: created on first call, reused afterwards (warm starts)."""
    global dynamodb, table
    if table is None:
        dynamodb = boto3.resource("dynamodb")
        table = dynamodb.Table(os.environ["TABLE_NAME"])
    return table


def unwrap(record: dict[str, Any]) -> dict[str, Any]:
    """Return the measurement from an envelope {call_id, type, emitted_at, data}.

    Legacy records (the measurement at top level, no `data`) are accepted as-is,
    so publisher and consumer can be deployed independently.
    """
    if isinstance(record.get("data"), dict):
        energy_event = dict(record["data"])
        # Keep the envelope metadata on the stored item for traceability
        energy_event["call_id"] = record.get("call_id")
        energy_event["emitted_at"] = record.get("emitted_at")
        return energy_event
    return record


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, int]:
    """Process a batch of Kinesis records.

    Pipeline per record:
    1. Decode, unwrap & parse (rejected if malformed -> poison pill protection)
    2. Dedup on event_id (within batch)
    3. Filter negative power readings (faulty sensor)
    4. Batch write valid events to DynamoDB (idempotent on sensor_id + event_timestamp)
    """
    seen_ids: set[str] = set()
    valid_events: list[dict[str, Any]] = []
    duplicates = 0
    negatives = 0
    rejected = 0

    for record in event["Records"]:
        # 1. Decode + unwrap + minimal validation (poison-pill protection)
        try:
            payload = base64.b64decode(record["kinesis"]["data"])
            energy_event = unwrap(json.loads(payload))
            event_id = energy_event["event_id"]
            power_kw = energy_event["measurements"]["power_kw"]
            # Align the field with the table's range key
            energy_event["event_timestamp"] = energy_event["timestamp"]
        except (KeyError, json.JSONDecodeError, TypeError, AttributeError) as exc:
            rejected += 1
            print(f"REJECTED: {exc!r}")
            continue

        # 2. Dedup on event_id (intra-batch)
        if event_id in seen_ids:
            duplicates += 1
            continue
        seen_ids.add(event_id)

        # 3. Filter negative readings (faulty sensor)
        if power_kw < 0:
            negatives += 1
            continue

        valid_events.append(energy_event)

    # 4. Write to DynamoDB
    written = write_to_dynamodb(valid_events)

    print(f"Batch: {len(event['Records'])} received | {duplicates} duplicates | "
          f"{negatives} negatives | {rejected} rejected | {written} written")

    return {
        "received": len(event["Records"]),
        "duplicates": duplicates,
        "negatives": negatives,
        "rejected": rejected,
        "written": written,
    }


def write_to_dynamodb(events: list[dict[str, Any]]) -> int:
    """Batch write events to DynamoDB. Floats are converted to Decimal."""
    if not events:
        return 0

    with _get_table().batch_writer() as batch:
        for event in events:
            item = json.loads(json.dumps(event), parse_float=Decimal)
            batch.put_item(Item=item)

    return len(events)
