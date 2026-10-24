"""Cross-repository API v1 regressions adapted from companion draft #15."""

from datetime import timedelta
from types import SimpleNamespace

import pytest
from homeassistant.config_entries import ConfigEntryState
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ev_charge_manager.price_consumer import PriceConsumer


@pytest.mark.parametrize("day,count", [("2026-03-29", 92), ("2026-10-24", 96), ("2026-10-25", 100)])
async def test_real_producer_api_contract_dst_and_site_isolation(hass, monkeypatch, day, count):
    import os
    from pathlib import Path

    import custom_components

    source = Path(os.environ.get("PRICE_ENGINE_SOURCE", "price-engine-reference")).resolve()
    assert (source / "custom_components/ha_energy_price_engine/api.py").exists()
    monkeypatch.setattr(
        custom_components,
        "__path__",
        [*custom_components.__path__, str(source / "custom_components")],
    )
    from datetime import date

    from custom_components.ha_energy_price_engine.models import PriceSlot as ProducerSlot
    from custom_components.ha_energy_price_engine.price_engine import PriceEngine, day_bounds

    start, end = day_bounds(date.fromisoformat(day))
    now = start - timedelta(hours=1)
    engine = PriceEngine(hass, "real_producer_contract")
    slots = []
    cursor = start
    while cursor < end:
        slots.append(ProducerSlot(cursor, cursor + timedelta(minutes=15), -0.25))
        cursor += timedelta(minutes=15)
    await engine.async_update("producer_home", slots, {"mode": "all_in"}, {"provider": "test"}, now)
    coordinator = SimpleNamespace(
        site={
            "id": "producer_home",
            "name": "Home",
            "area": "DK2",
            "timezone": "Europe/Copenhagen",
        },
        price_engine=engine,
        schedule=SimpleNamespace(
            days={"producer_home": {day: {"status": "READY", "last_success": now.isoformat()}}}
        ),
    )
    producer = MockConfigEntry(domain="ha_energy_price_engine", data={"id": "producer_home"})
    producer.add_to_hass(hass)
    producer.mock_state(hass, ConfigEntryState.LOADED)
    hass.data["ha_energy_price_engine"] = {producer.entry_id: coordinator}
    consumer = PriceConsumer(hass)
    site = {
        "id": "ev_home",
        "producer_entry": producer.entry_id,
        "producer_site": "producer_home",
        "timezone": "Europe/Copenhagen",
    }
    # Exercise the real producer API with an exact local-day DST range.
    result = consumer.lookup(site, start, end, now)
    assert len(result) == count and all(s.price == -0.25 for s in result)
    coordinator.schedule.days["producer_home"][day]["status"] = "STALE"
    with pytest.raises(ValueError, match="STALE"):
        consumer.lookup(site, start, end, now)
    coordinator.schedule.days["producer_home"][day]["status"] = "READY"
    site["producer_site"] = "another_site"
    with pytest.raises(ValueError, match="ownership"):
        consumer.lookup(site, start, end, now)
    producer.mock_state(hass, ConfigEntryState.NOT_LOADED)
