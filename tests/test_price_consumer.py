"""Strict normalized snapshots and native producer API integration."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ev_charge_manager.price_consumer import DOMAIN, EVENT, decode

from .test_manager import model

NOW = datetime(2026, 10, 24, 12, tzinfo=UTC)


def response(entry, site, start, end, price=1):
    slots = []
    cursor = start
    while cursor < end:
        slots.append(
            {
                "start": cursor.isoformat(),
                "end": (cursor + timedelta(minutes=15)).isoformat(),
                "final_price_incl_vat": price,
            }
        )
        cursor += timedelta(minutes=15)
    return {
        "api_version": 1,
        "producer_entry_id": entry,
        "site_id": site,
        "currency": "DKK",
        "unit": "DKK/kWh",
        "vat_included": True,
        "revision": 1,
        "status": "READY",
        "verified_at": NOW.isoformat(),
        "slots": slots,
    }


def api_result(data):
    """Frozen producer API shape, not an HA service response."""
    rows = tuple(
        SimpleNamespace(
            site_id=data["site_id"],
            start=datetime.fromisoformat(r["start"]),
            end=datetime.fromisoformat(r["end"]),
            currency="DKK",
            unit="DKK/kWh",
            final_price_incl_vat=r["final_price_incl_vat"],
        )
        for r in data["slots"]
    )
    return SimpleNamespace(
        api_version=data["api_version"],
        site_id=data["site_id"],
        status=data["status"],
        revision=data["revision"],
        last_success=data["verified_at"],
        reason=None,
        records=rows,
        expected_slots=len(rows),
        valid_slots=len(rows),
    )


@pytest.mark.parametrize(
    "change",
    [
        {"api_version": 2},
        {"api_version": True},
        {"site_id": "other"},
        {"producer_entry_id": "wrong"},
        {"currency": "EUR"},
        {"unit": "DKK/MWh"},
        {"vat_included": 1},
        {"vat_included": False},
        {"status": "STALE"},
        {"revision": -1},
        {"verified_at": (NOW - timedelta(days=2)).isoformat()},
    ],
)
def test_contract_rejects_ambiguity(change):
    data = response("producer", "home", NOW, NOW + timedelta(hours=1))
    data.update(change)
    with pytest.raises(ValueError):
        decode(data, "producer", "home", NOW, NOW, NOW + timedelta(hours=1))


def test_negative_prices_and_partial_gaps_are_not_zero_filled():
    data = response("producer", "home", NOW, NOW + timedelta(hours=1), -0.2)
    assert decode(data, "producer", "home", NOW, NOW, NOW + timedelta(hours=1))[0][0].price == -0.2
    data["slots"].pop(1)
    with pytest.raises(ValueError):
        decode(data, "producer", "home", NOW, NOW, NOW + timedelta(hours=1))
    data["status"] = "INCOMPLETE"
    assert len(decode(data, "producer", "home", NOW, NOW, NOW + timedelta(hours=1))[0]) == 3


async def test_native_consumer_no_embedded_producer_and_revision_event(hass, freezer):
    freezer.move_to(NOW)
    config = model(hass)
    producer = MockConfigEntry(domain=DOMAIN, data={"id": "producer_home"})
    producer.add_to_hass(hass)
    producer.mock_state(hass, ConfigEntryState.LOADED)
    config["sites"][0] = {
        "id": "home",
        "name": "Home",
        "timezone": "Europe/Copenhagen",
        "zone_state": "home",
        "grid_kw": 11,
        "price_source": "energy_price_engine",
        "producer_entry": producer.entry_id,
        "producer_site": "producer_home",
    }
    calls = []

    def lookup(site, start, end, **kwargs):
        calls.append((site, start, end))
        return api_result(response(producer.entry_id, site, start, end))

    entry = MockConfigEntry(domain="ev_charge_manager", data=config)
    entry.add_to_hass(hass)
    with (
        patch("custom_components.ev_charge_manager.price_consumer.import_module") as module,
        patch(
            "custom_components.ev_charge_manager.price_update.PriceUpdater.refresh",
            new_callable=AsyncMock,
        ) as embedded,
        patch(
            "custom_components.ev_charge_manager.price_engine.calculate",
            side_effect=AssertionError("EV price arithmetic"),
        ),
    ):
        module.return_value.get_api.return_value.lookup.side_effect = lookup
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        c = entry.runtime_data
        assert c.data["forecasts"]["home"]["car"].valid
        assert len(calls) == 2
        assert c.price_schedule.cancel is None
        embedded.assert_not_called()
        for _ in range(3):
            await c.async_refresh()
        assert len(calls) == 2
        hass.bus.async_fire(
            EVENT,
            {
                "api_version": 1,
                "producer_entry_id": producer.entry_id,
                "site_id": "another",
                "revision": 2,
            },
        )
        await hass.async_block_till_done()
        assert len(calls) == 2
        hass.bus.async_fire(
            EVENT,
            {
                "api_version": 1,
                "producer_entry_id": producer.entry_id,
                "site_id": "producer_home",
                "revision": 2,
            },
        )
        await hass.async_block_till_done()
        assert len(calls) == 4
        hass.bus.async_fire(
            EVENT,
            {
                "api_version": 1,
                "producer_entry_id": producer.entry_id,
                "site_id": "producer_home",
                "revision": 2,
            },
        )
        await hass.async_block_till_done()
        assert len(calls) == 4  # Duplicate pending revision is coalesced.
        producer.mock_state(hass, ConfigEntryState.NOT_LOADED)
        await c.async_refresh()  # Unload invalidates within the 60-second lookup throttle.
        assert not c.data["forecasts"]["home"]["car"].valid
        assert c.data["price_status"]["home"]["status"] == "ERROR"
        assert await hass.config_entries.async_unload(entry.entry_id)


def test_shared_producer_example_fixture():
    import json
    from pathlib import Path

    data = json.loads(
        (Path(__file__).parents[1] / "docs/contracts/example-response-v1.json").read_text()
    )
    start = datetime(2026, 10, 24, 12, tzinfo=UTC)
    result, _ = decode(
        data, "producer-entry", "producer-site", start, start, start + timedelta(minutes=15)
    )
    assert result[0].price == 1.25


def test_consumed_all_in_prices_preserve_earliest_tolerance_ties():
    from dataclasses import replace

    from custom_components.ev_charge_manager.planner import plan_site

    from .test_planner import V

    data = response("producer", "home", NOW, NOW + timedelta(minutes=45))
    for row, amount in zip(data["slots"], [2, 1.004, 1], strict=True):
        row["final_price_incl_vat"] = amount
    slots, _ = decode(data, "producer", "home", NOW, NOW, NOW + timedelta(minutes=45))
    forecast = plan_site(
        [replace(V, target=61)],
        slots,
        NOW,
        timezone="Europe/Copenhagen",
        grid_kw=10,
        boost_enabled=False,
    )["car"]
    assert forecast.valid
    assert forecast.allocations[0].start == NOW + timedelta(minutes=15)
    assert forecast.allocations[0].price == 1.004  # No extra VAT or unit conversion.


async def test_producer_error_preserves_reason_and_bounded_retry(hass):
    from custom_components.ev_charge_manager.price_consumer import PriceConsumer

    producer = MockConfigEntry(domain=DOMAIN, data={"id": "house"}, state=ConfigEntryState.LOADED)
    producer.add_to_hass(hass)
    consumer = PriceConsumer(hass)
    site = {
        "id": "home",
        "producer_entry": producer.entry_id,
        "producer_site": "house",
        "timezone": "Europe/Copenhagen",
    }
    with patch(
        "custom_components.ev_charge_manager.price_consumer.import_module",
        side_effect=TimeoutError(),
    ) as module:
        await consumer.refresh(site, NOW)
        await consumer.refresh(site, NOW)
        assert module.call_count == 1
    assert consumer.slots(site, NOW) == ()
    assert consumer.status["home"]["status"] == "ERROR"
    assert consumer.status["home"]["reason"] == "TimeoutError"
    producer.mock_state(hass, ConfigEntryState.NOT_LOADED)


async def test_native_site_configuration_contains_consumer_mapping_not_tariffs(hass):
    from custom_components.ev_charge_manager.config_flow import defaults

    producer = MockConfigEntry(domain=DOMAIN, data={"id": "producer_home"})
    producer.add_to_hass(hass)
    entry = MockConfigEntry(domain="ev_charge_manager", data=defaults())
    entry.add_to_hass(hass)
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    fid = flow["flow_id"]
    flow = await hass.config_entries.options.async_configure(fid, {"next_step_id": "site"})
    assert flow["step_id"] == "site"
    flow = await hass.config_entries.options.async_configure(
        fid,
        {
            "id": "home",
            "name": "Home",
            "zone_state": "home",
            "timezone": "Europe/Copenhagen",
            "grid_kw": 11,
            "producer_entry": producer.entry_id,
            "producer_site": "producer-home",
        },
    )
    assert flow["type"] == "menu"
    await hass.config_entries.options.async_configure(fid, {"next_step_id": "finish"})
    site = entry.options["sites"][0]
    assert site["price_source"] == "energy_price_engine"
    assert "tariff" not in site and "nordpool_entry" not in site


@pytest.mark.parametrize("status", ["INCOMPLETE", "STALE", "ERROR", "NOT_LOADED"])
async def test_public_api_degraded_status_never_uses_legacy_or_partial_prices(hass, status):
    from custom_components.ev_charge_manager.price_consumer import PriceConsumer

    producer = MockConfigEntry(domain=DOMAIN, data={"id": "home"}, state=ConfigEntryState.LOADED)
    producer.add_to_hass(hass)
    site = {
        "id": "home",
        "producer_entry": producer.entry_id,
        "producer_site": "home",
        "timezone": "UTC",
    }
    result = api_result(response(producer.entry_id, "home", NOW, NOW + timedelta(hours=36)))
    result.status = status
    consumer = PriceConsumer(hass)
    with patch("custom_components.ev_charge_manager.price_consumer.import_module") as module:
        module.return_value.get_api.return_value.lookup.return_value = result
        await consumer.refresh(site, NOW)
    assert not consumer.slots(site, NOW)
    assert status in consumer.status["home"]["reason"]
    producer.mock_state(hass, ConfigEntryState.NOT_LOADED)


async def test_public_api_revision_rollback_clears_usable_prices(hass):
    from custom_components.ev_charge_manager.price_consumer import PriceConsumer

    producer = MockConfigEntry(domain=DOMAIN, data={"id": "home"}, state=ConfigEntryState.LOADED)
    producer.add_to_hass(hass)
    site = {
        "id": "home",
        "producer_entry": producer.entry_id,
        "producer_site": "home",
        "timezone": "UTC",
    }
    consumer = PriceConsumer(hass)
    with patch("custom_components.ev_charge_manager.price_consumer.import_module") as module:
        api = module.return_value.get_api.return_value
        api.lookup.side_effect = lambda site, start, end, **kw: api_result(
            response(producer.entry_id, site, start, end)
        )
        await consumer.refresh(site, NOW)
        assert consumer.slots(site, NOW)
        consumer.revisions["home"] = 2
        await consumer.refresh(site, NOW, force=True)
        assert not consumer.slots(site, NOW)
        assert "rollback" in consumer.status["home"]["reason"]
    producer.mock_state(hass, ConfigEntryState.NOT_LOADED)


async def test_unpublished_tomorrow_does_not_discard_verified_today(hass):
    from custom_components.ev_charge_manager.price_consumer import PriceConsumer

    producer = MockConfigEntry(domain=DOMAIN, data={"id": "home"}, state=ConfigEntryState.LOADED)
    producer.add_to_hass(hass)
    site = {
        "id": "home",
        "producer_entry": producer.entry_id,
        "producer_site": "home",
        "timezone": "UTC",
    }
    consumer = PriceConsumer(hass)
    midnight = NOW.replace(hour=0) + timedelta(days=1)

    def lookup(site, start, end, **kwargs):
        data = api_result(response(producer.entry_id, site, start, end, -0.25))
        if end > midnight:
            data.status = "INCOMPLETE"
        return data

    with patch("custom_components.ev_charge_manager.price_consumer.import_module") as module:
        module.return_value.get_api.return_value.lookup.side_effect = lookup
        await consumer.refresh(site, NOW)
    slots = consumer.slots(site, NOW)
    assert slots and slots[-1].end == midnight
    assert all(slot.price == -0.25 for slot in slots)
    assert consumer.status["home"]["status"] == "INCOMPLETE"
    assert "INCOMPLETE" in consumer.status["home"]["reason"]
    producer.mock_state(hass, ConfigEntryState.NOT_LOADED)
