"""Kinesis client: publish and read events on a stream."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.core.exceptions import ExternalServiceError

logger = logging.getLogger(__name__)

# Kinesis limit: at most 500 records per put_records call
MAX_RECORDS_PER_CALL = 500


def default_partition_key(envelope: dict[str, Any]) -> str:
    """PartitionKey = sensor_id of the wrapped event (per-sensor ordering)."""
    return envelope["data"]["sensor_id"]


@dataclass(frozen=True, slots=True)
class PublishResult:
    sent: int
    failed: int


class KinesisClient:
    def __init__(self, stream_name: str, region: str, boto_client: Any | None = None) -> None:
        self.stream_name = stream_name
        self._client = boto_client or boto3.client("kinesis", region_name=region)

    def publish(self, records: list[dict[str, Any]],
                partition_key: Callable[[dict[str, Any]], str] = default_partition_key) -> PublishResult:
        """Send records in chunks of 500."""
        sent = failed = 0

        for start in range(0, len(records), MAX_RECORDS_PER_CALL):
            chunk = records[start:start + MAX_RECORDS_PER_CALL]
            entries = [
                {"Data": json.dumps(record).encode("utf-8"), "PartitionKey": partition_key(record)}
                for record in chunk
            ]
            try:
                response = self._client.put_records(StreamName=self.stream_name, Records=entries)
            except (BotoCoreError, ClientError) as exc:
                raise ExternalServiceError(f"put_records failed on {self.stream_name}: {exc}") from exc

            chunk_failed = response["FailedRecordCount"]
            failed += chunk_failed
            sent += len(entries) - chunk_failed

        logger.info("Sent: %d/%d | Failed: %d", sent, len(records), failed)
        return PublishResult(sent=sent, failed=failed)

    def read_from_start(self, shard_id: str = "shardId-000000000000", limit: int = 100) -> list[dict[str, Any]]:
        """Read the shard from TRIM_HORIZON until caught up with the tip (debugging tool)."""
        iterator = self._client.get_shard_iterator(
            StreamName=self.stream_name,
            ShardId=shard_id,
            ShardIteratorType="TRIM_HORIZON",
        )["ShardIterator"]

        records: list[dict[str, Any]] = []
        while iterator:
            response = self._client.get_records(ShardIterator=iterator, Limit=limit)
            batch = response["Records"]
            records.extend(json.loads(record["Data"]) for record in batch)

            if not batch and response.get("MillisBehindLatest", 0) == 0:
                break
            iterator = response.get("NextShardIterator")

        logger.info("%d records read from %s", len(records), self.stream_name)
        return records
