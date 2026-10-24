"""API contract, fail-closed simulation and consumer-only price ownership."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ev_charge_manager.price_consumer import REVISION_EVENT, PriceConsumer

from .test_manager import model


def response(site, start, end):
    cursor = start
    records = []
    while cursor < end:
        records.append(
            SimpleNamespace(
                site_id=site,
                start=cursor,
                end=cursor + timedelta(minutes=15),
                currency="DKK",
                unit="DKK/kWh",
                final_price_incl_vat=-0.25,
            )
        )
        cursor += timedelta(minutes=15)
    return SimpleNamespace(
        api_version=1,
        site_id=site,
        status="READY",
        records=tuple(records),
        expected_slots=len(records),
        valid_slots=len(records),
        revision=7,
        last_success=start.isoformat(),
        reason=None,
    )


@pytest.mark.parametrize("status", ["INCOMPLETE", "STALE", "ERROR", "NOT_LOADED"])
async def test_degraded_producer_never_becomes_free_or_legacy_price(hass, status):
    now = datetime(2026, 10, 24, tzinfo=UTC)
    data = response("producer_home", now, now + timedelta(hours=1))
    data.status = status
    api = Mock()
    api.lookup.return_value = data
    with patch("custom_components.ev_charge_manager.price_consumer.import_module") as module:
        module.return_value.get_api.return_value = api
        result = PriceConsumer(hass).lookup("producer_home", now, now + timedelta(hours=1), now)
    assert result.status == status and not result.slots


async def test_final_prices_are_copied_unchanged_and_discovery_backs_off(hass):
    now = datetime(2026, 10, 24, tzinfo=UTC)
    consumer = PriceConsumer(hass)
    with patch(
        "custom_components.ev_charge_manager.price_consumer.import_module", side_effect=ImportError
    ) as module:
        assert consumer.lookup("home", now, now + timedelta(hours=1), now).status == "NOT_LOADED"
        assert (
            consumer.lookup(
                "home", now, now + timedelta(hours=1), now + timedelta(seconds=1)
            ).status
            == "NOT_LOADED"
        )
        assert module.call_count == 1
    api = Mock()
    api.lookup.return_value = response("home", now, now + timedelta(hours=1))
    consumer.invalidate_discovery()
    with patch("custom_components.ev_charge_manager.price_consumer.import_module") as module:
        module.return_value.get_api.return_value = api
        result = consumer.lookup("home", now, now + timedelta(hours=1), now)
    assert result.status == "READY" and [s.price for s in result.slots] == [-0.25] * 4
    assert result.revision == 7
    module.return_value.get_api.assert_called_once_with(hass, version=1)
    assert sorted(result.slots, key=lambda s: (s.price, s.start))[0].start == now


@pytest.mark.parametrize("bad", ["site", "unit", "coverage", "nonfinite", "version"])
async def test_malformed_producer_contract_rejected(hass, bad):
    now = datetime(2026, 10, 24, tzinfo=UTC)
    data = response("home", now, now + timedelta(hours=1))
    if bad == "site":
        data.records[0].site_id = "other"
    if bad == "unit":
        data.records[0].unit = "ore/kWh"
    if bad == "coverage":
        data.records = data.records[:1]
    if bad == "nonfinite":
        data.records[0].final_price_incl_vat = float("nan")
    if bad == "version":
        data.api_version = 2
    with patch("custom_components.ev_charge_manager.price_consumer.import_module") as module:
        module.return_value.get_api.return_value.lookup.return_value = data
        result = PriceConsumer(hass).lookup("home", now, now + timedelta(hours=1), now)
    assert result.status == "ERROR" and not result.slots


async def test_native_manager_consumer_never_fetches_or_composes_and_reacts_to_revision(
    hass, freezer
):
    freezer.move_to("2026-10-23T12:00:00Z")
    config = model(hass)
    config["sites"][0].pop("price_entity")
    config["sites"][0]["price_engine_site"] = "producer_home"
    api = Mock()
    api.lookup.side_effect = lambda site, start, end, **kwargs: response(site, start, end)
    with (
        patch("custom_components.ev_charge_manager.price_consumer.import_module") as module,
        patch(
            "custom_components.ev_charge_manager.price_update.PriceUpdater.refresh",
            side_effect=AssertionError("consumer fetch"),
        ),
        patch(
            "custom_components.ev_charge_manager.price_engine.calculate",
            side_effect=AssertionError("consumer arithmetic"),
        ),
    ):
        module.return_value.get_api.return_value = api
        entry = MockConfigEntry(domain="ev_charge_manager", data=config)
        entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        c = entry.runtime_data
        assert c.data["forecasts"]["home"]["car"].valid
        assert c.data["price_status"]["home"]["revision"] == 7
        assert not c.price_engine.records
        assert not c.price_schedule.days
        old = api.lookup.call_count
        hass.bus.async_fire(
            REVISION_EVENT, {"api_version": 1, "site_id": "producer_home", "revision": 8}
        )
        await hass.async_block_till_done()
        assert api.lookup.call_count > old
        api.lookup.side_effect = lambda site, start, end, **kwargs: SimpleNamespace(
            **{**response(site, start, end).__dict__, "status": "STALE"}
        )
        await c.async_refresh()
        assert not c.data["forecasts"]["home"]["car"].valid
        assert c.sites["home"].price_slots is None
        assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize("day,count", [("2026-03-29", 92), ("2026-10-24", 96), ("2026-10-25", 100)])
async def test_real_producer_api_contract_dst_and_site_isolation(hass, monkeypatch, day, count):
    import os
    from pathlib import Path

    import custom_components

    source = Path(os.environ.get("PRICE_ENGINE_SOURCE", "price-engine-reference")).resolve()
    assert (source / "custom_components/ha_energy_price_engine/api.py").exists(), (
        "Set PRICE_ENGINE_SOURCE to the pinned producer checkout (see docs/price-engine-consumer.md)"
    )
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
    hass.data["ha_energy_price_engine"] = {"test": coordinator}
    consumer = PriceConsumer(hass)
    with patch(
        "custom_components.ha_energy_price_engine.price_engine.calculate",
        side_effect=AssertionError("consumer recalculation"),
    ):
        result = consumer.lookup("producer_home", start, end, now)
        assert result.status == "READY" and len(result.slots) == count
        assert all(s.price == -0.25 for s in result.slots)
        assert consumer.lookup("other_site", start, end, now).status == "NOT_LOADED"
        coordinator.schedule.days["producer_home"][day]["status"] = "STALE"
        assert not consumer.lookup("producer_home", start, end, now).slots


async def test_native_ui_external_source_is_explicit_and_exclusive(hass):
    from homeassistant.data_entry_flow import FlowResultType

    flow = await hass.config_entries.flow.async_init(
        "ev_charge_manager", context={"source": "user"}
    )
    fid = flow["flow_id"]
    flow = await hass.config_entries.flow.async_configure(fid, {"next_step_id": "site"})
    data = {
        "id": "home",
        "name": "Home",
        "zone_state": "home",
        "timezone": "Europe/Copenhagen",
        "grid_kw": 11,
        "price_engine_site": "producer_home",
        "price_entity": "sensor.legacy",
        "price_attribute": "slots",
        "price_multiplier": 1,
        "area": "DK2",
        "price_basis": "spot_ex_vat",
        "grid": 0,
        "tax": 0,
        "supplier": 0,
        "vat": 0.25,
    }
    flow = await hass.config_entries.flow.async_configure(fid, data)
    assert flow["errors"]["base"] == "invalid_mapping"
    data.pop("price_entity")
    flow = await hass.config_entries.flow.async_configure(fid, data)
    assert flow["type"] == FlowResultType.MENU
    with patch("custom_components.ev_charge_manager.async_setup_entry", return_value=True):
        flow = await hass.config_entries.flow.async_configure(fid, {"next_step_id": "finish"})
        await hass.async_block_till_done()
    assert flow["type"] == FlowResultType.CREATE_ENTRY
    site = flow["data"]["sites"][0]
    assert site["price_engine_site"] == "producer_home"
    assert site["tariff"] == {"mode": "all_in"}  # No local VAT or tariff additions.
