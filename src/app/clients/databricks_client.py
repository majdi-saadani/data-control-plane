"""Minimal client for the Databricks Jobs API (REST 2.1)."""

from __future__ import annotations

from typing import Any

import httpx

from app.core.exceptions import ExternalServiceError, NotFoundError


class DatabricksClient:
    def __init__(self, host: str, token: str, timeout_s: float = 30.0,
                 http_client: httpx.Client | None = None) -> None:
        self._http = http_client or httpx.Client(
            base_url=host.rstrip("/"),
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout_s,
        )

    def find_job_id(self, job_name: str) -> int:
        """Resolve a job name (as shown in the UI) to its job_id. Names must be unique."""
        response = self._request("GET", "/api/2.1/jobs/list", params={"name": job_name, "limit": 25})
        matches = [job for job in response.get("jobs", []) if job.get("settings", {}).get("name") == job_name]
        if not matches:
            raise NotFoundError(f"Databricks job '{job_name}' not found")
        if len(matches) > 1:
            raise ExternalServiceError(f"Databricks job name '{job_name}' is ambiguous ({len(matches)} jobs)")
        return int(matches[0]["job_id"])

    def run_now(self, job_id: int, job_parameters: dict[str, str] | None = None) -> dict[str, Any]:
        """Trigger an existing job. Returns {"run_id": ..., "number_in_job": ...}."""
        body: dict[str, Any] = {"job_id": job_id}
        if job_parameters:
            body["job_parameters"] = job_parameters
        return self._request("POST", "/api/2.1/jobs/run-now", json=body)

    def get_run(self, run_id: int) -> dict[str, Any]:
        """Fetch the state of a run."""
        return self._request("GET", "/api/2.1/jobs/runs/get", params={"run_id": run_id})

    def cancel_run(self, run_id: int) -> None:
        self._request("POST", "/api/2.1/jobs/runs/cancel", json={"run_id": run_id})

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = self._http.request(method, path, **kwargs)
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise ExternalServiceError(
                f"Databricks {method} {path} -> {exc.response.status_code}: {exc.response.text}"
            ) from exc
        except httpx.HTTPError as exc:
            raise ExternalServiceError(f"Databricks unreachable ({method} {path}): {exc}") from exc
        return response.json() if response.content else {}
