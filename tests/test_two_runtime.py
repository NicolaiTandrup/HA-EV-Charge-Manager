"""Actual PE/CM startup, revision and unload harness adapted from pinned PE #7.

Reuses tools/test_two_runtime.py at bb71585654b431e61aa256657ab18d8c0f571cf0.
All source data is synthetic; services are forbidden and no production HA accessed.
"""

import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from .test_manager import model


@pytest.fixture
def hass_config_dir(tmp_path):
    return str(tmp_path)


@pytest.mark.parametrize("producer_first", [True, False], ids=["producer-first", "consumer-first"])
async def test_two_real_runtimes(
    hass, freezer, enable_custom_integrations, monkeypatch, producer_first
):
    import custom_components

    source = Path(os.environ.get("PRICE_ENGINE_SOURCE", "price-engine-reference")).resolve()
    assert (source / "custom_components/ha_energy_price_engine/api.py").exists()
    monkeypatch.setattr(
        custom_components,
        "__path__",
        [*custom_components.__path__, str(source / "custom_components")],
    )
    monkeypatch.setenv("PE_CONSUMER_LINE", "current")
    from custom_components.ha_energy_price_engine.const import DOMAIN
    from custom_components.ha_energy_price_engine.price_engine import day_bounds

    freezer.move_to("2026-10-23T12:00:00Z")
    now = datetime(2026, 10, 23, 12, tzinfo=UTC)
    raw = []
    for day in (date(2026, 10, 23), date(2026, 10, 24)):
        cursor, end = day_bounds(day)
        while cursor < end:
            raw.append(
                {
                    "start": cursor.isoformat(),
                    "end": (cursor + timedelta(minutes=15)).isoformat(),
                    "price": 1.25,
                }
            )
            cursor += timedelta(minutes=15)
    attributes = {
        "slots": raw,
        "currency": "DKK",
        "unit_of_measurement": "DKK/kWh",
        "vat_included": True,
        "verified_at": now.isoformat(),
    }
    hass.states.async_set("sensor.beta_price", "1.25", attributes)
    pe = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        unique_id="house",
        data={
            "id": "house",
            "name": "House",
            "area": "DK2",
            "timezone": "Europe/Copenhagen",
            "source_type": "entity",
            "price_entity": "sensor.beta_price",
            "price_unit": "DKK/kWh",
            "price_basis": "all_in",
            "vat": 0.25,
            "dated_components": [],
            "dso_mode": "manual",
        },
    )
    pe.add_to_hass(hass)
    if producer_first:
        assert await hass.config_entries.async_setup(pe.entry_id)
        await hass.async_block_till_done()
        assert pe.runtime_data.data["status"] == "READY"
    config = model(hass)
    if os.environ["PE_CONSUMER_LINE"] == "pr15":
        config["sites"][0].pop("price_entity")
        config["sites"][0]["price_engine_site"] = "house"
    else:
        config["sites"][0] = {
            "id": "home",
            "name": "Home",
            "zone_state": "home",
            "timezone": "Europe/Copenhagen",
            "grid_kw": 11,
            "price_source": "energy_price_engine",
            "producer_entry": pe.entry_id,
            "producer_site": "house",
        }
    cm = MockConfigEntry(domain="ev_charge_manager", data=config)
    cm.add_to_hass(hass)
    with (
        patch(
            "homeassistant.core.ServiceRegistry.async_call",
            side_effect=AssertionError("unexpected service/control call"),
        ),
        patch(
            "custom_components.ev_charge_manager.price_engine.calculate",
            side_effect=AssertionError("consumer recomposition"),
        ),
        patch(
            "custom_components.ev_charge_manager.price_update.PriceUpdater.refresh",
            side_effect=AssertionError("consumer fetch"),
        ),
    ):
        assert await hass.config_entries.async_setup(cm.entry_id)
        await hass.async_block_till_done()
        if not producer_first:
            assert cm.runtime_data.data["price_status"]["home"]["status"] != "READY"
            assert not cm.runtime_data.data["forecasts"]["home"]["car"].valid
            assert await hass.config_entries.async_setup(pe.entry_id)
            await hass.async_block_till_done()
            freezer.tick(timedelta(seconds=65))
            async_fire_time_changed(hass)
            await hass.async_block_till_done()
            now = dt_util.utcnow()
        assert cm.runtime_data.data["price_status"]["home"]["status"] == "READY"
        forecast = cm.runtime_data.data["forecasts"]["home"]["car"]
        assert forecast.valid and all(a.price == 1.25 for a in forecast.allocations)
        freezer.tick(timedelta(seconds=10))
        now = now + timedelta(seconds=10)
        changed = {
            **attributes,
            "slots": [{**row, "price": 2.5} for row in raw],
            "verified_at": now.isoformat(),
        }
        hass.states.async_set("sensor.beta_price", "2.5", changed)
        for day in (date(2026, 10, 23), date(2026, 10, 24)):
            await pe.runtime_data.schedule.refresh_day(pe.runtime_data.site, day, now)
        await hass.async_block_till_done()
        revision = pe.runtime_data.price_engine.revisions["house"]
        # HA's existing coordinator debouncer coalesces adjacent day revisions.
        # Advance its bounded cooldown, then require the final durable revision.
        freezer.tick(timedelta(seconds=11))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
        assert cm.runtime_data.data["price_status"]["home"]["revision"] == revision
        assert cm.runtime_data.data["forecasts"]["home"]["car"].valid
        with patch(
            "custom_components.ev_charge_manager.optimizer.plan_site",
            side_effect=AssertionError("duplicate replan"),
        ):
            hass.bus.async_fire(
                "ha_energy_price_engine_price_revision_v1",
                {
                    "api_version": 1,
                    "producer_entry_id": pe.entry_id,
                    "site_id": "house",
                    "revision": revision,
                },
            )
            await hass.async_block_till_done()
        assert await hass.config_entries.async_unload(pe.entry_id)
        await cm.runtime_data.async_refresh()
        assert not cm.runtime_data.data["forecasts"]["home"]["car"].valid
        assert await hass.config_entries.async_unload(cm.entry_id)
        await hass.async_block_till_done()
