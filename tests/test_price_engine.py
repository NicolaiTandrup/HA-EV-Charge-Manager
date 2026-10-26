"""Persistent prices are calculated on updates and immutable across lookups."""

from datetime import UTC, date, datetime, timedelta
from unittest.mock import patch

import pytest

from custom_components.ev_charge_manager.planner import PriceSlot
from custom_components.ev_charge_manager.price_engine import PriceEngine, day_bounds

NOW = datetime(2026, 10, 23, tzinfo=UTC)


def rows(day=date(2026, 10, 24)):
    start, end = day_bounds(day)
    result = []
    while start < end:
        result.append(PriceSlot(start, start + timedelta(minutes=15), -0.1))
        start += timedelta(minutes=15)
    return result


@pytest.mark.parametrize(
    "day,count", [(date(2026, 3, 29), 92), (date(2026, 10, 25), 100), (date(2026, 10, 24), 96)]
)
async def test_day_shape_dst_and_restart(hass, day, count):
    engine = PriceEngine(hass, "test")
    data = rows(day)
    assert len(data) == count
    await engine.async_update(
        "home",
        data,
        {"mode": "spot_ex_vat", "grid": 0.2, "vat": 0.25},
        {"provider": "test"},
        NOW - timedelta(days=365),
    )
    restored = PriceEngine(hass, "test")
    await restored.async_load(["home"])
    assert restored.complete_day("home", day)
    with patch(
        "custom_components.ev_charge_manager.price_engine.calculate",
        side_effect=AssertionError("read recalculation"),
    ):
        result = restored.lookup("home", *day_bounds(day))
        assert len(result) == count and result[0].final_price_incl_vat == pytest.approx(0.125)


async def test_unchanged_no_calculation_or_write_and_past_preserved(hass):
    engine = PriceEngine(hass, "test")
    data = rows()
    tariff = {"mode": "all_in"}
    await engine.async_update("home", data, tariff, {}, NOW)
    with patch(
        "custom_components.ev_charge_manager.price_engine.calculate",
        side_effect=AssertionError("unchanged recalculation"),
    ):
        assert not await engine.async_update("home", data, tariff, {}, NOW)
    later = data[2].start
    corrected = [PriceSlot(s.start, s.end, 3) for s in data]
    await engine.async_update("home", corrected, tariff, {"version": "correction"}, later)
    result = engine.lookup("home", data[0].start, data[-1].end)
    assert result[0].final_price_incl_vat == -0.1
    assert result[2].final_price_incl_vat == 3
    assert result[0].revision == 1 and result[2].revision == 2


async def test_invalid_atomic_batch_and_separate_sites(hass):
    engine = PriceEngine(hass, "test")
    data = rows()
    await engine.async_update("home", data, {"mode": "all_in"}, {}, NOW)
    with pytest.raises(ValueError):
        await engine.async_update("home", data + data[:1], {"mode": "all_in"}, {}, NOW)
    assert engine.complete_day("home", date(2026, 10, 24))
    assert not engine.complete_day("away", date(2026, 10, 24))
    with patch("homeassistant.helpers.storage.Store.async_save", side_effect=OSError("disk full")):
        with pytest.raises(OSError):
            await engine.async_update("away", data, {"mode": "all_in"}, {}, NOW)
    assert engine.lookup("away", *day_bounds(date(2026, 10, 24))) == ()


async def test_concurrent_updates_and_verification_only_changes_are_noops(hass):
    from asyncio import gather

    engine = PriceEngine(hass, "concurrent")
    data = rows()
    args = ("home", data, {"mode": "all_in"}, {"provider": "test", "verified_at": "first"}, NOW)
    assert await gather(engine.async_update(*args), engine.async_update(*args)) == [True, False]
    with patch(
        "custom_components.ev_charge_manager.price_engine.calculate",
        side_effect=AssertionError("verification-only calculation"),
    ):
        assert not await engine.async_update(
            "home", data, {"mode": "all_in"}, {"provider": "test", "verified_at": "later"}, NOW
        )


async def test_optimizer_and_sensor_reads_never_fetch_or_recalculate(hass):
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from .test_manager import model

    entry = MockConfigEntry(domain="ev_charge_manager", data=model(hass))
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    c = entry.runtime_data
    with (
        patch(
            "custom_components.ev_charge_manager.price_engine.calculate",
            side_effect=AssertionError("consumer calculation"),
        ),
        patch.object(c.price_updater, "refresh", side_effect=AssertionError("consumer fetch")),
    ):
        for _ in range(4):
            await c.async_refresh()
            assert c.data["forecasts"]["home"]["car"].valid
            c.price_engine.lookup("home", NOW, NOW + timedelta(days=1))
    assert await hass.config_entries.async_unload(entry.entry_id)
