"""CLI: generate and publish events without going through the API.

Usage (from the repo root):
    python -m app.cli --count 20 --seed 42 [--dry-run]     # with PYTHONPATH=src
"""

import argparse
import json

from app.api.dependencies import get_event_sender
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.domain.event_generator import generate_events
from app.schemas.events import SendEventsRequest


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic energy sensor events.")
    parser.add_argument("--count", type=int, default=20, help="Number of events to emit (default: 20)")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility")
    parser.add_argument("--dry-run", action="store_true", help="Print events without publishing")
    args = parser.parse_args()

    configure_logging()

    if args.dry_run:
        for event in generate_events(count=args.count, seed=args.seed):
            print(json.dumps(event.to_dict(), ensure_ascii=False))

    service = get_event_sender(get_settings())
    result = service.send(SendEventsRequest(count=args.count, seed=args.seed, dry_run=args.dry_run))
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
