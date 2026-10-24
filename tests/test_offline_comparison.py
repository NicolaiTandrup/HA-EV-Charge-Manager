"""Migration comparison never fetches, zero fills or assumes household tariffs."""

import json
import runpy
from pathlib import Path

import pytest

compare = runpy.run_path(str(Path(__file__).parents[1] / "scripts/compare_price_exports.py"))[
    "compare"
]


def export(path, amount=-0.25):
    value = {
        "schema_version": 1,
        "site_id": "synthetic",
        "timezone": "Europe/Copenhagen",
        "currency": "DKK",
        "unit": "DKK/kWh",
        "vat_included": True,
        "slots": [
            {
                "start": "2026-10-25T00:00:00+00:00",
                "end": "2026-10-25T00:15:00+00:00",
                "final_price_incl_vat": amount,
            }
        ],
    }
    path.write_text(json.dumps(value))
    return value


def test_offline_exact_match_and_real_zero_are_not_missing(tmp_path):
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    export(a, 0)
    export(b, 0)
    assert compare(a, b)["passed"]
    export(b, -0.25)
    assert compare(a, b)["price_mismatches"] == 1


def test_wrong_site_ambiguous_vat_and_coverage_fail(tmp_path):
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    export(a)
    data = export(b)
    data["site_id"] = "other"
    b.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="Site"):
        compare(a, b)
    data = export(b)
    data["vat_included"] = 1
    b.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        compare(a, b)
    data = export(b)
    data["slots"][0].update(start="2026-10-25T00:15:00+00:00", end="2026-10-25T00:30:00+00:00")
    b.write_text(json.dumps(data))
    result = compare(a, b)
    assert not result["passed"] and result["missing_candidate_slots"] == 1
