"""/databricks endpoints: trigger and monitor jobs."""

from fastapi import APIRouter, status

from app.api.dependencies import DatabricksRunnerDep
from app.schemas.databricks import RunJobRequest, RunJobResponse, RunStatusResponse

router = APIRouter(prefix="/databricks", tags=["databricks"])


@router.post("/jobs/{job_id}/run", response_model=RunJobResponse, status_code=status.HTTP_202_ACCEPTED)
def run_job(job_id: int, service: DatabricksRunnerDep, request: RunJobRequest | None = None) -> RunJobResponse:
    """Trigger an existing Databricks job (asynchronous: returns the run_id to poll)."""
    params = request.job_parameters if request else {}
    return service.run_job(job_id, params)


@router.get("/runs/{run_id}", response_model=RunStatusResponse)
def get_run_status(run_id: int, service: DatabricksRunnerDep) -> RunStatusResponse:
    """Status of a Databricks run."""
    return service.get_run_status(run_id)
