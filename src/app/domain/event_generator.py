"""Energy sensor event generator.

Generates synthetic energy sensor events for a streaming ingestion pipeline.
Intentionally injects data quality issues to exercise downstream processing:
- Duplicate events (same event, emitted twice)  -> dedup logic
- Negative measurements (faulty sensor)         -> filtering logic

Used by the POST /events/send endpoint (via EventSenderService) and by the app.cli CLI.
"""

from __future__ import annotations

import random
import uuid
from datetime import datetime, timedelta, timezone

from app.domain.energy_event import EnergyEvent

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SENSOR_IDS: tuple[str, ...] = (
    "SENS-FR-IDF-0001",
    "SENS-FR-IDF-0002",
    "SENS-FR-IDF-0003",
    "SENS-FR-HDF-0010",
    "SENS-FR-PAC-0021",
)

SITE_BY_SENSOR: dict[str, str] = {
    "SENS-FR-IDF-0001": "SITE-PARIS-EST",
    "SENS-FR-IDF-0002": "SITE-PARIS-EST",
    "SENS-FR-IDF-0003": "SITE-CRETEIL",
    "SENS-FR-HDF-0010": "SITE-LILLE",
    "SENS-FR-PAC-0021": "SITE-MARSEILLE",
}

DUPLICATE_RATIO: float = 0.15   # ~15% of events are re-emitted as exact duplicates
NEGATIVE_RATIO: float = 0.15    # ~15% of events carry a negative (faulty) measurement

# ---------------------------------------------------------------------------
# Generation logic
# ---------------------------------------------------------------------------

def _base_load_kw(at: datetime) -> float:
    """Realistic daily load curve: low at night, peaks around 12h and 19h."""
    hour = at.hour + at.minute / 60
    morning_peak = 30 * pow(2.718, -((hour - 12) ** 2) / 8)
    evening_peak = 45 * pow(2.718, -((hour - 19) ** 2) / 6)
    night_base = 12.0
    return night_base + morning_peak + evening_peak


def _make_event(rng: random.Random, at: datetime, *, negative: bool = False) -> EnergyEvent:
    sensor_id = rng.choice(SENSOR_IDS)
    power_kw = round(_base_load_kw(at) * rng.uniform(0.85, 1.15), 2)

    if negative:
        # Simulate a faulty sensor reading to be filtered downstream.
        power_kw = -abs(power_kw)

    voltage_v = round(rng.gauss(mu=230.0, sigma=2.5), 1)
    current_a = round(abs(power_kw) * 1000 / max(voltage_v, 1.0), 1)

    return EnergyEvent(
        event_id=str(uuid.UUID(int=rng.getrandbits(128), version=4)),
        sensor_id=sensor_id,
        site_id=SITE_BY_SENSOR[sensor_id],
        timestamp=at.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        power_kw=power_kw,
        energy_kwh=round(rng.uniform(1000, 5000), 2),
        voltage_v=voltage_v,
        current_a=current_a,
        frequency_hz=round(rng.gauss(mu=50.0, sigma=0.05), 3),
        temperature_c=round(rng.uniform(25.0, 55.0), 1),
        status="FAULT" if negative else "OK",
    )


def generate_events(count: int = 20, seed: int | None = None) -> list[EnergyEvent]:
    """Generate `count` events, including duplicates and negative values.

    The returned list has exactly `count` elements. Duplicates are exact
    copies of previously generated events (same event_id, same payload),
    mimicking an at-least-once delivery from a message broker.
    """
    rng = random.Random(seed)
    now = datetime.now(timezone.utc)

    n_duplicates = max(1, int(count * DUPLICATE_RATIO))
    n_negatives = max(1, int(count * NEGATIVE_RATIO))
    n_originals = count - n_duplicates

    events: list[EnergyEvent] = []
    negative_slots = set(rng.sample(range(n_originals), k=min(n_negatives, n_originals)))

    for i in range(n_originals):
        at = now - timedelta(seconds=rng.randint(0, 3600))
        events.append(_make_event(rng, at, negative=i in negative_slots))

    # Re-emit some existing events as exact duplicates (at-least-once delivery).
    duplicates = rng.choices(events, k=n_duplicates)
    events.extend(duplicates)

    rng.shuffle(events)
    return events


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic energy sensor events.")
    parser.add_argument("--count", type=int, default=20, help="Number of events to emit (default: 20)")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility")
    args = parser.parse_args()

    events = generate_events(count=args.count, seed=args.seed)

    for event in events:
        print(json.dumps(event.to_dict(), ensure_ascii=False))

    payloads = [event.to_dict() for event in events]
    publish_events(events=payloads)


    # Summary on stderr-like footer (kept on stdout for simplicity here).
    unique_ids = {e.event_id for e in events}
    negatives = sum(1 for e in events if e.power_kw < 0)
    print(
        f"\n--- {len(events)} events | {len(events) - len(unique_ids)} duplicates "
        f"| {negatives} negative readings ---"
    )


if __name__ == "__main__":
    main()

# python -m events_publisher.energy_sensor.energy_sensor_publisher