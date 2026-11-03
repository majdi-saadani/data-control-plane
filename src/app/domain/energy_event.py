from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class EnergyEvent:
    """A single measurement emitted by an energy sensor."""

    event_id: str
    sensor_id: str
    site_id: str
    timestamp: str  # ISO 8601 UTC
    power_kw: float
    energy_kwh: float
    voltage_v: float
    current_a: float
    frequency_hz: float
    temperature_c: float
    status: str = field(default="OK")

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "sensor_id": self.sensor_id,
            "site_id": self.site_id,
            "timestamp": self.timestamp,
            "measurements": {
                "power_kw": self.power_kw,
                "energy_kwh": self.energy_kwh,
                "voltage_v": self.voltage_v,
                "current_a": self.current_a,
                "frequency_hz": self.frequency_hz,
            },
            "temperature_c": self.temperature_c,
            "status": self.status,
        }