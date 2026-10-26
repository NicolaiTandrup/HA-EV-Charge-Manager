#!/usr/bin/env python3
"""Offline portable CM fixture replay. No HA connection, credentials or commands."""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from custom_components.ev_charge_manager.dev_simulation import scenarios, simulate  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=list(scenarios()), default="two_tesla_two_easee")
    parser.add_argument("--at", help="Optional aware ISO time; defaults to current UTC")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = simulate(
        args.scenario, datetime.fromisoformat(args.at) if args.at else datetime.now(UTC)
    )
    encoded = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.write_text(encoded)
    else:
        print(encoded, end="")


if __name__ == "__main__":
    main()
