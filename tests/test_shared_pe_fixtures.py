"""Unmodified producer-owned v1 machine fixtures through real producer and CM.

Fixture/test approach reused from PE #7 tests/test_consumer_interoperability.py;
source pin and provenance are documented in docs/contracts/price-consumer-v1.md.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ev_charge_manager.price_consumer import PriceConsumer

ROOT = Path(__file__).parents[1]
CASES = json.loads((ROOT / "docs/contracts/price-api-v1.examples.json").read_text())["scenarios"]


@pytest.mark.parametrize("case", CASES, ids=lambda x: x["name"])
async def test_exact_producer_machine_fixture_without_consumer_io(
    hass, monkeypatch, tmp_path, case
):
    import custom_components

    source = Path(os.environ.get("PRICE_ENGINE_SOURCE", "price-engine-reference")).resolve()
    assert (source / "custom_components/ha_energy_price_engine/api.py").exists()
    monkeypatch.setattr(
        custom_components,
        "__path__",
        [*custom_components.__path__, str(source / "custom_components")],
    )
    monkeypatch.setattr(hass.config, "config_dir", str(tmp_path))
    from custom_components.ha_energy_price_engine.api import get_api, serialize_result
    from custom_components.ha_energy_price_engine.models import PriceSlot
    from custom_components.ha_energy_price_engine.price_engine import PriceEngine

    request, expected = case["request"], case["response"]
    producer = MockConfigEntry(
        domain="ha_energy_price_engine",
        entry_id=request["producer_entry_id"],
        data={"id": request["site_id"]},
    )
    producer.add_to_hass(hass)
    producer.mock_state(hass, ConfigEntryState.LOADED)
    now = datetime.fromisoformat(request["now"])
    start, end = datetime.fromisoformat(request["start"]), datetime.fromisoformat(request["end"])
    engine = PriceEngine(hass, producer.entry_id)
    slots = [
        PriceSlot(
            datetime.fromisoformat(r["start"]),
            datetime.fromisoformat(r["end"]),
            r["final_price_incl_vat"],
        )
        for r in expected["slots"]
    ]
    await engine.async_update(
        request["site_id"], slots, {"mode": "all_in"}, {"verified_at": now.isoformat()}, now
    )
    coordinator = SimpleNamespace(
        site={
            "id": request["site_id"],
            "name": "Synthetic",
            "area": "DK2",
            "timezone": "Europe/Copenhagen",
        },
        price_engine=engine,
        schedule=SimpleNamespace(
            days={
                request["site_id"]: {
                    case["name"][:10]: {
                        "status": expected["status"],
                        "last_success": now.isoformat(),
                    }
                }
            }
        ),
    )
    hass.data["ha_energy_price_engine"] = {producer.entry_id: coordinator}
    actual = serialize_result(
        get_api(hass, version=1).lookup(
            request["site_id"], start, end, now=now, producer_entry_id=producer.entry_id
        )
    )
    assert actual == expected  # Exact producer-owned fixture; no local tariff assumptions.
    site = {
        "id": "consumer",
        "producer_entry": producer.entry_id,
        "producer_site": request["site_id"],
        "timezone": "Europe/Copenhagen",
    }
    with (
        patch(
            "custom_components.ha_energy_price_engine.price_engine.calculate",
            side_effect=AssertionError("Consumer price arithmetic"),
        ),
        patch.object(
            engine.database, "async_load", side_effect=AssertionError("Consumer database read")
        ),
        patch.object(
            engine.database, "async_commit", side_effect=AssertionError("Consumer database write")
        ),
    ):
        if expected["status"] == "READY":
            rows = PriceConsumer(hass).lookup(site, start, end, now)
            assert [(s.start, s.end, s.price) for s in rows] == [
                (s.start, s.end, s.price) for s in slots
            ]
        else:
            with pytest.raises(ValueError, match=expected["status"]):
                PriceConsumer(hass).lookup(site, start, end, now)
    producer.mock_state(hass, ConfigEntryState.NOT_LOADED)
