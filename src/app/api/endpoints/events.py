"""/events endpoints: send sensor events to Kinesis."""

from fastapi import APIRouter

from app.api.dependencies import EventSenderDep
from app.schemas.events import SendEventsRequest, SendEventsResponse

router = APIRouter(prefix="/events", tags=["events"])


@router.post("/send", response_model=SendEventsResponse)
def send_events(request: SendEventsRequest, service: EventSenderDep) -> SendEventsResponse:
    """Generate `count` events (~15% duplicates, ~15% negative readings) and publish them to Kinesis."""
    return service.send(request)
