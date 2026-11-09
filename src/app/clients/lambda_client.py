"""AWS Lambda client: synchronous invocation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.core.exceptions import ExternalServiceError


@dataclass(frozen=True, slots=True)
class InvocationResult:
    request_id: str
    status_code: int
    function_error: str | None      # e.g. "Unhandled" when the function raised
    payload: Any                    # decoded JSON returned by the function

    @property
    def succeeded(self) -> bool:
        return self.function_error is None and 200 <= self.status_code < 300


class LambdaClient:
    def __init__(self, region: str, boto_client: Any | None = None) -> None:
        self._client = boto_client or boto3.client("lambda", region_name=region)

    def invoke(self, function_name: str, payload: dict[str, Any]) -> InvocationResult:
        """Invoke synchronously (RequestResponse) and return the decoded result."""
        try:
            response = self._client.invoke(
                FunctionName=function_name,
                InvocationType="RequestResponse",
                Payload=json.dumps(payload).encode("utf-8"),
            )
        except (BotoCoreError, ClientError) as exc:
            raise ExternalServiceError(f"Lambda invoke failed on {function_name}: {exc}") from exc

        raw = response["Payload"].read()
        try:
            decoded = json.loads(raw) if raw else None
        except json.JSONDecodeError:
            decoded = raw.decode("utf-8", errors="replace")

        return InvocationResult(
            request_id=response.get("ResponseMetadata", {}).get("RequestId", ""),
            status_code=response.get("StatusCode", 0),
            function_error=response.get("FunctionError"),
            payload=decoded,
        )
