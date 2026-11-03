"""Kinesis client: publish and read events on a stream."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.core.exceptions import ExternalServiceError

logger = logging.getLogger(__name__)

# Kinesis limit: at most 500 records per put_records call
MAX_RECORDS_PER_CALL = 500


@dataclass(frozen=True, slots=True)
class PublishResult:
    sent: int
    failed: int


class KinesisClient:
    def __init__(self, stream_name: str, region: str, boto_client: Any | None = None) -> None:
        self.stream_name = stream_name
        self._client = boto_client or boto3.client("kinesis", region_name=region)

    def publish(self, events: list[dict[str, Any]], partition_key_field: str = "sensor_id") -> PublishResult:
        """Send events in chunks of 500. PartitionKey = sensor_id (per-sensor ordering)."""
        sent = failed = 0

        for start in range(0, len(events), MAX_RECORDS_PER_CALL):
            chunk = events[start:start + MAX_RECORDS_PER_CALL]
            records = [
                {
                    "Data": json.dumps(event).encode("utf-8"),
                    "PartitionKey": event[partition_key_field],
                }
                for event in chunk
            ]
            try:
                response = self._client.put_records(StreamName=self.stream_name, Records=records)
            except (BotoCoreError, ClientError) as exc:
                raise ExternalServiceError(f"put_records failed on {self.stream_name}: {exc}") from exc

            chunk_failed = response["FailedRecordCount"]
            failed += chunk_failed
            sent += len(records) - chunk_failed

        logger.info("Sent: %d/%d | Failed: %d", sent, len(events), failed)
        return PublishResult(sent=sent, failed=failed)

    def read_from_start(self, shard_id: str = "shardId-000000000000", limit: int = 100) -> list[dict[str, Any]]:
        """Read the shard from TRIM_HORIZON until caught up with the tip (debugging tool)."""
        iterator = self._client.get_shard_iterator(
            StreamName=self.stream_name,
            ShardId=shard_id,
            ShardIteratorType="TRIM_HORIZON",
        )["ShardIterator"]

        events: list[dict[str, Any]] = []
        while iterator:
            response = self._client.get_records(ShardIterator=iterator, Limit=limit)
            records = response["Records"]
            events.extend(json.loads(record["Data"]) for record in records)

            if not records and response.get("MillisBehindLatest", 0) == 0:
                break
            iterator = response.get("NextShardIterator")

        logger.info("%d records read from %s", len(events), self.stream_name)
        return events
