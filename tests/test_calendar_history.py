"""Calendar reports contain observed samples only, with exact midnight splitting."""

from datetime import UTC, datetime, timedelta

import pytest

from custom_components.ev_charge_manager.history import History
from custom_components.ev_charge_manager.planner import PriceSlot


def test_midnight_energy_cost_credit_and_calendar_periods():
    now = datetime(2026, 10, 24, 21, 59, tzinfo=UTC)  # Copenhagen 23:59 before DST.
    h = History()
    prices = [
        PriceSlot(now - timedelta(minutes=14), now + timedelta(minutes=1), 2),
        PriceSlot(now + timedelta(minutes=1), now + timedelta(minutes=16), -1),
    ]
    h.sample_power(now, 6, True, prices, timezone="Europe/Copenhagen")
    h.sample_power(now + timedelta(minutes=2), 6, True, prices, timezone="Europe/Copenhagen")
    assert h.daily["2026-10-24"]["energy_kwh"] == pytest.approx(0.1)
    assert h.daily["2026-10-25"]["energy_kwh"] == pytest.approx(0.1)
    assert h.daily["2026-10-24"]["cost"] == pytest.approx(0.2)
    assert h.daily["2026-10-25"]["cost"] == pytest.approx(-0.1)
    report_now = now + timedelta(minutes=2)
    assert h.period_total("energy_kwh", "day", report_now) == pytest.approx(0.1)
    assert h.period_total("energy_kwh", "week", report_now) == pytest.approx(0.2)
    assert h.period_total("cost", "year", report_now) == pytest.approx(0.1)
    restored = History(**h.persistent())
    assert restored.daily == h.daily
    restored.sample_power(report_now + timedelta(days=1), 6, True, [], timezone="Europe/Copenhagen")
    assert restored.energy_kwh == h.energy_kwh  # No restart extrapolation.


def test_old_lifetime_is_not_assigned_invented_calendar_dates():
    h = History(energy_kwh=500, cost=100, distance_km=3000)
    now = datetime(2026, 10, 24, tzinfo=UTC)
    assert h.period_total("energy_kwh", "month", now) == 0
    h.sample_odometer("odo", 10000, "km", now=now, timezone="Europe/Copenhagen")
    h.sample_odometer(
        "odo", 10004, "km", now=now + timedelta(hours=1), timezone="Europe/Copenhagen"
    )
    assert h.period_total("distance_km", "day", now + timedelta(hours=1)) == 4
    assert h.distance_km == 3004


def test_unpriced_and_calendar_boundaries_never_become_free():
    h = History()
    now = datetime(2026, 12, 31, 23, 59, tzinfo=UTC)
    h.sample_power(now, 6, True, [])
    h.sample_power(now + timedelta(minutes=2), 6, True, [])
    assert h.period_total("unpriced_energy_kwh", "year", now) == pytest.approx(0.1)
    assert h.period_total(
        "unpriced_energy_kwh", "year", now + timedelta(minutes=2)
    ) == pytest.approx(0.1)
    assert h.cost == 0 and h.unpriced_energy_kwh == pytest.approx(0.2)


async def test_native_period_sensors_and_persistence(hass, freezer):
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.ev_charge_manager.sensor import MeasuredSensor

    from .test_manager import model

    freezer.move_to("2026-10-24T12:00:00Z")
    config = model(hass)
    entry = MockConfigEntry(domain="ev_charge_manager", data=config)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    c = entry.runtime_data
    h = c.sites["home"].history["car"]
    now = datetime(2026, 10, 24, 12, tzinfo=UTC)
    h.sample_power(now, 6, True, [], timezone="Europe/Copenhagen")
    h.sample_power(now + timedelta(minutes=1), 6, True, [], timezone="Europe/Copenhagen")
    for period in ("day", "week", "month", "year"):
        sensor = MeasuredSensor(c, "car", "unpriced_energy_kwh", "home", period)
        assert sensor.native_value == pytest.approx(0.1)
        assert sensor.last_reset.tzinfo is not None
        assert sensor.extra_state_attributes["calendar_coverage"] == "observed_buckets_only"
    await c.async_save()
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert await hass.config_entries.async_setup(entry.entry_id)
    assert entry.runtime_data.sites["home"].history["car"].daily == h.daily
    assert await hass.config_entries.async_unload(entry.entry_id)
