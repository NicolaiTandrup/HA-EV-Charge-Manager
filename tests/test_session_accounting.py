"""Session totals attribute existing measurements; they never re-integrate power."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from custom_components.ev_charge_manager.session_accounting import SessionAccounting

NOW = datetime(2026, 10, 26, 12, tzinfo=UTC)


def session(vehicle="car"):
    return SimpleNamespace(
        id="plug",
        vehicle=vehicle,
        last_verified_connected=NOW.isoformat(),
        source_device="physical",
    )


def test_identity_boundary_and_unmeasured_guest_never_rewrite_old_costs(hass):
    book = SessionAccounting(hass, "unit")
    book.loaded = True
    book.reconcile(
        {"charger": session()},
        [{"id": "charger", "zone_state": "home"}],
        [{"id": "home", "zone_state": "home", "timezone": "Europe/Copenhagen"}],
        NOW,
    )
    first = book.active_for("charger")
    book.add(
        first["id"],
        {"energy_kwh": 1, "cost": -0.25, "unpriced_energy_kwh": 0},
        {"2026-10-26": {"energy_kwh": 1, "cost": -0.25, "unpriced_energy_kwh": 0}},
        NOW,
        "source",
        [],
    )
    book.reconcile(
        {"charger": session("other")},
        [{"id": "charger", "zone_state": "home"}],
        [{"id": "home", "zone_state": "home", "timezone": "Europe/Copenhagen"}],
        NOW + timedelta(minutes=1),
    )
    second = book.active_for("charger")
    assert second["id"] != first["id"]
    assert first["totals"]["cost"] == -0.25
    assert first["ended_reason"] == "association_boundary"
    assert second["measured_intervals"] == 0
    with pytest.raises(ValueError, match="immutable"):
        book.add(
            first["id"],
            {"energy_kwh": 1, "cost": 99, "unpriced_energy_kwh": 0},
            {},
            NOW,
            "source",
            [],
        )
    assert book.totals_for("charger", None, NOW)["cost"] == -0.25


async def test_restart_creates_new_observation_segment_without_backfill(hass):
    book = SessionAccounting(hass, "restart")
    await book.async_load()
    chargers = [{"id": "charger", "zone_state": "home"}]
    sites = [{"id": "home", "zone_state": "home", "timezone": "Europe/Copenhagen"}]
    book.reconcile({"charger": session()}, chargers, sites, NOW)
    first = book.active_for("charger")
    await book.async_save()
    restored = SessionAccounting(hass, "restart")
    await restored.async_load()
    restored.reconcile({"charger": session()}, chargers, sites, NOW + timedelta(hours=1))
    assert restored.active_for("charger")["id"] != first["id"]
    assert restored.records[first["id"]]["ended_reason"] == "restart_unverified"
    assert restored.totals_for("charger", None, NOW)["energy_kwh"] == 0


async def test_runtime_deltas_are_not_double_counted_or_bridged_across_replug(hass, freezer):
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from .test_manager import model

    freezer.move_to(NOW)
    config = model(hass)
    hass.states.async_set("sensor.car_charging", "on")
    hass.states.async_set("sensor.car_power", "6", {"unit_of_measurement": "kW"})
    entry = MockConfigEntry(domain="ev_charge_manager", data=config)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    c = entry.runtime_data
    first = c.accounting.active_for("charger")
    freezer.tick(timedelta(minutes=1))
    hass.states.async_set("sensor.car_power", "6", {"unit_of_measurement": "kW"})
    await c.async_refresh()
    assert first["totals"]["energy_kwh"] == pytest.approx(0.1)
    assert first["totals"]["cost"] == pytest.approx(0.1)
    assert first["measured_intervals"] == 1
    await c.async_refresh()
    assert first["measured_intervals"] == 1  # Watchdog is not a meter report.
    hass.states.async_set("sensor.charger", "disconnected")
    await c.async_refresh()
    freezer.tick(timedelta(minutes=1))
    hass.states.async_set("sensor.charger", "charging")
    hass.states.async_set("sensor.car_power", "6", {"unit_of_measurement": "kW"})
    await c.async_refresh()
    second = c.accounting.active_for("charger")
    assert second["id"] != first["id"]
    assert second["measured_intervals"] == 0
    assert c.sites["home"].history["car"].energy_kwh == pytest.approx(0.1)
    freezer.tick(timedelta(minutes=1))
    hass.states.async_set("sensor.car_power", "6", {"unit_of_measurement": "kW"})
    hass.states.async_set("sensor.car_cable", "on")
    hass.states.async_set("sensor.car_charging", "on")
    await c.async_refresh()
    total = c.accounting.totals_for("charger", None, NOW)
    assert total["energy_kwh"] == pytest.approx(0.2)
    assert c.sites["home"].history["car"].energy_kwh == pytest.approx(0.2)
    assert first["totals"]["cost"] == pytest.approx(0.1)
    assert first["ended_reason"] == "connection_boundary"
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_native_session_and_charger_totals_show_missing_meter_as_unavailable(hass):
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.ev_charge_manager.sensor import ChargerAccountingSensor

    from .test_manager import model

    config = model(hass)
    hass.states.async_set("sensor.car_cable", "off")
    entry = MockConfigEntry(domain="ev_charge_manager", data=config)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    c = entry.runtime_data
    sensor = ChargerAccountingSensor(c, config["chargers"][0], "energy_kwh", "session")
    assert not sensor.available and sensor.native_value is None
    assert sensor.extra_state_attributes["unknown_meter_is_zero"] is False
    assert sensor.extra_state_attributes["unmeasured_segments"] == 1
    row = c.accounting.active_for("charger")
    assert row["basis"] == "unmeasured_unknown_vehicle"
    assert row["measured_intervals"] == 0
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_corrupt_accounting_is_preserved_and_not_replaced(hass):
    from pathlib import Path

    book = SessionAccounting(hass, "corrupt")
    path = Path(book.store.path)
    await hass.async_add_executor_job(path.parent.mkdir, 0o700, True, True)
    await hass.async_add_executor_job(path.write_text, "{corrupt")
    await book.async_load()
    assert book.storage_error and not book.loaded
    await book.async_save()
    assert await hass.async_add_executor_job(path.read_text) == "{corrupt"


async def test_cached_pre_restart_power_is_not_a_post_restart_baseline(hass, freezer):
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from .test_manager import model

    freezer.move_to(NOW)
    config = model(hass)
    hass.states.async_set("sensor.car_charging", "on")
    hass.states.async_set("sensor.car_power", "6", {"unit_of_measurement": "kW"})
    entry = MockConfigEntry(domain="ev_charge_manager", data=config)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    freezer.tick(timedelta(minutes=1))
    hass.states.async_set("sensor.car_power", "6", {"unit_of_measurement": "kW"})
    await entry.runtime_data.async_refresh()
    assert await hass.config_entries.async_unload(entry.entry_id)
    freezer.tick(timedelta(minutes=1))
    assert await hass.config_entries.async_setup(entry.entry_id)
    c = entry.runtime_data
    freezer.tick(timedelta(seconds=30))
    for field, value in [("power", "6"), ("cable", "on"), ("charging", "on")]:
        hass.states.async_set(
            "sensor.car_" + field, value, {"unit_of_measurement": "kW"} if field == "power" else {}
        )
    await c.async_refresh()
    assert c.sites["home"].history["car"].energy_kwh == pytest.approx(0.1)
    freezer.tick(timedelta(seconds=30))
    hass.states.async_set("sensor.car_power", "6", {"unit_of_measurement": "kW"})
    await c.async_refresh()
    assert c.sites["home"].history["car"].energy_kwh == pytest.approx(0.15)
    assert c.accounting.totals_for("charger", None, NOW)["energy_kwh"] == pytest.approx(0.15)
    assert await hass.config_entries.async_unload(entry.entry_id)
