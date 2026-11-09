"""/events endpoints: send sensor events to Kinesis."""

from fastapi import APIRouter, Request

from app.api.dependencies import EventSenderDep
from app.schemas.events import SendEventsRequest, SendEventsResponse

router = APIRouter(prefix="/events", tags=["events"])


@router.post("/send", response_model=SendEventsResponse)
def send_events(body: SendEventsRequest, request: Request, service: EventSenderDep) -> SendEventsResponse:
    """Generate `count` events (~15% duplicates, ~15% negative readings) and publish them to Kinesis.

    Every record is wrapped in the envelope {call_id, type, emitted_at, data};
    call_id is this request's X-Request-ID.
    """
    return service.send(body, call_id=request.state.request_id)
