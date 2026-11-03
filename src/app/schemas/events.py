"""Request/response schemas for the /events endpoints."""

from pydantic import BaseModel, Field


class SendEventsRequest(BaseModel):
    count: int = Field(default=20, ge=1, le=5000, description="Number of events to generate")
    seed: int | None = Field(default=None, description="Random seed (reproducibility)")
    dry_run: bool = Field(default=False, description="Generate without publishing to Kinesis")


class SendEventsResponse(BaseModel):
    stream_name: str
    generated: int
    duplicates: int
    negatives: int
    sent: int
    failed: int
    dry_run: bool
