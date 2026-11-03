"""Service: generate synthetic sensor events and publish them to Kinesis."""

from __future__ import annotations

from app.clients.kinesis_client import KinesisClient
from app.domain.event_generator import generate_events
from app.schemas.events import SendEventsRequest, SendEventsResponse


class EventSenderService:
    def __init__(self, kinesis: KinesisClient) -> None:
        self._kinesis = kinesis

    def send(self, request: SendEventsRequest) -> SendEventsResponse:
        events = generate_events(count=request.count, seed=request.seed)
        payloads = [event.to_dict() for event in events]

        sent = failed = 0
        if not request.dry_run:
            result = self._kinesis.publish(payloads)
            sent, failed = result.sent, result.failed

        return SendEventsResponse(
            stream_name=self._kinesis.stream_name,
            generated=len(events),
            duplicates=len(events) - len({e.event_id for e in events}),
            negatives=sum(1 for e in events if e.power_kw < 0),
            sent=sent,
            failed=failed,
            dry_run=request.dry_run,
        )
