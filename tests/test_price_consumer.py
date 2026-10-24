"""Public producer contract: mocks only; no actual producer implementation exists."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import SupportsResponse
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
    producer = MockConfigEntry(domain=DOMAIN)
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

    async def get_prices(call):
        calls.append(dict(call.data))
        return response(
            producer.entry_id,
            "producer_home",
            datetime.fromisoformat(call.data["start"]),
            datetime.fromisoformat(call.data["end"]),
        )

    hass.services.async_register(
        DOMAIN, "get_prices", get_prices, supports_response=SupportsResponse.ONLY
    )
    entry = MockConfigEntry(domain="ev_charge_manager", data=config)
    entry.add_to_hass(hass)
    with (
        patch(
            "custom_components.ev_charge_manager.price_update.PriceUpdater.refresh",
            new_callable=AsyncMock,
        ) as embedded,
        patch(
            "custom_components.ev_charge_manager.price_engine.calculate",
            side_effect=AssertionError("EV price arithmetic"),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        c = entry.runtime_data
        assert c.data["forecasts"]["home"]["car"].valid
        assert len(calls) == 1
        assert c.price_schedule.cancel is None
        embedded.assert_not_called()
        for _ in range(3):
            await c.async_refresh()
        assert len(calls) == 1
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
        assert len(calls) == 1
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
        assert len(calls) == 2  # Duplicate pending revision is coalesced.
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
