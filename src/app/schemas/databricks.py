"""Request/response schemas for the /databricks endpoints."""

from pydantic import BaseModel, Field


class RunJobRequest(BaseModel):
    job_parameters: dict[str, str] = Field(default_factory=dict, description="Parameters passed to the job")


class RunJobResponse(BaseModel):
    job_id: int
    run_id: int


class RunStatusResponse(BaseModel):
    run_id: int
    life_cycle_state: str | None = None    # PENDING, RUNNING, TERMINATED...
    result_state: str | None = None        # SUCCESS, FAILED... (once terminated)
    state_message: str | None = None
    run_page_url: str | None = None
