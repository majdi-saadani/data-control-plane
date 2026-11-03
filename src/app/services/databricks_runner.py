"""Service: trigger and monitor Databricks jobs."""

from __future__ import annotations

from app.clients.databricks_client import DatabricksClient
from app.schemas.databricks import RunJobResponse, RunStatusResponse


class DatabricksRunnerService:
    def __init__(self, client: DatabricksClient) -> None:
        self._client = client

    def run_job(self, job_id: int, job_parameters: dict[str, str]) -> RunJobResponse:
        response = self._client.run_now(job_id, job_parameters)
        return RunJobResponse(job_id=job_id, run_id=response["run_id"])

    def get_run_status(self, run_id: int) -> RunStatusResponse:
        run = self._client.get_run(run_id)
        state = run.get("state", {})
        return RunStatusResponse(
            run_id=run_id,
            life_cycle_state=state.get("life_cycle_state"),
            result_state=state.get("result_state"),
            state_message=state.get("state_message"),
            run_page_url=run.get("run_page_url"),
        )
