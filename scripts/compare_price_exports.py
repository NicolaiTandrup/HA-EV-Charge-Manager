#!/usr/bin/env python3
"""Offline migration evidence only; no fetch, tariff arithmetic or HA connection."""

import argparse
import json
import math
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


def read_export(path):
    data = json.loads(Path(path).read_text())
    if (
        type(data.get("schema_version")) is not int
        or data["schema_version"] != 1
        or data.get("currency") != "DKK"
        or data.get("unit") != "DKK/kWh"
        or data.get("vat_included") is not True
        or not data.get("site_id")
    ):
        raise ValueError("Explicit site and final inclusive DKK/kWh export v1 required")
    ZoneInfo(data["timezone"])
    rows = {}
    for row in data["slots"]:
        start, end = (datetime.fromisoformat(row[k]) for k in ("start", "end"))
        amount = row["final_price_incl_vat"]
        if (
            start.tzinfo is None
            or end.tzinfo is None
            or start.timestamp() % 900
            or end.timestamp() - start.timestamp() != timedelta(minutes=15).total_seconds()
            or isinstance(amount, bool)
            or not isinstance(amount, (int, float))
            or not math.isfinite(amount)
            or start.timestamp() in rows
        ):
            raise ValueError("Malformed, duplicate or non-quarter price interval")
        rows[start.timestamp()] = amount
    if not rows:
        raise ValueError("An empty export is not price verification")
    return data, rows


def compare(left, right, tolerance=0.000001):
    if not math.isfinite(tolerance) or tolerance < 0:
        raise ValueError("Tolerance must be finite and nonnegative")
    a, old = read_export(left)
    b, new = read_export(right)
    if (a["site_id"], a["timezone"]) != (b["site_id"], b["timezone"]):
        raise ValueError("Site/timezone mismatch; do not compare another household")
    common = old.keys() & new.keys()
    differences = [abs(old[t] - new[t]) for t in common]
    missing, extra = len(old.keys() - new.keys()), len(new.keys() - old.keys())
    mismatch = sum(delta > tolerance for delta in differences)
    return {
        "legacy_slots": len(old),
        "candidate_slots": len(new),
        "common_slots": len(common),
        "missing_candidate_slots": missing,
        "extra_candidate_slots": extra,
        "price_mismatches": mismatch,
        "max_absolute_difference": max(differences, default=None),
        "tolerance_dkk_per_kwh": tolerance,
        "passed": bool(common) and not (missing or extra or mismatch),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("legacy_export")
    parser.add_argument("candidate_export")
    parser.add_argument("--tolerance", type=float, default=0.000001)
    args = parser.parse_args()
    try:
        result = compare(args.legacy_export, args.candidate_export, args.tolerance)
    except (ValueError, TypeError, KeyError, OSError) as error:
        parser.error(str(error))
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
