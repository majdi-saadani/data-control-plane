"""Event envelope: the wire format published to Kinesis.

Every record is wrapped as:
    {
      "call_id":    "<id of the API request / Lambda invocation that emitted it>",
      "type":       "energy.measurement",
      "emitted_at": "2026-11-09T10:00:00.000Z",
      "data":       { ...EnergyEvent.to_dict()... }
    }

The consumer Lambda unwraps `data`; `call_id` lets us trace every stored
measurement back to the call that produced it.
"""

from datetime import datetime, timezone
from typing import Any

ENERGY_MEASUREMENT_TYPE = "energy.measurement"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def wrap(data: dict[str, Any], call_id: str, event_type: str = ENERGY_MEASUREMENT_TYPE) -> dict[str, Any]:
    return {
        "call_id": call_id,
        "type": event_type,
        "emitted_at": utc_now_iso(),
        "data": data,
    }
