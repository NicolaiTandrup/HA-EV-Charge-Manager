"""Native measured totals, source identity and guest ownership regression."""

from datetime import timedelta

import pytest
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ev_charge_manager.history import History

from .test_manager import model, register_provider


def test_energy_without_prices_is_not_free_and_survives_restart():
    now = dt_util.utcnow()
    history = History()
    history.sample_power(now, 6, True, [])
    history.sample_power(now + timedelta(minutes=1), 6, True, [])
    assert history.energy_kwh == pytest.approx(0.1)
    assert history.unpriced_energy_kwh == pytest.approx(0.1) and history.cost == 0
    restored = History(**history.persistent())
    assert restored.unpriced_energy_kwh == history.unpriced_energy_kwh
    restored.sample_power(now + timedelta(days=1), 6, True, [])
    assert restored.energy_kwh == history.energy_kwh


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1])
def test_invalid_measurement_breaks_baseline(bad):
    now = dt_util.utcnow()
    h = History()
    h.sample_power(now, 6, True, [])
    h.sample_power(now + timedelta(seconds=60), bad, True, [])
    h.sample_power(now + timedelta(seconds=120), 6, True, [])
    assert h.energy_kwh == 0
    with pytest.raises(ValueError):
        History(energy_kwh=bad)


async def test_native_energy_cost_coverage_and_restart(hass, freezer):
    config = model(hass)
    hass.states.async_remove("sensor.prices")
    hass.states.async_set("sensor.car_charging", "on")
    hass.states.async_set("sensor.car_power", "6", {"unit_of_measurement": "kW"})
    entry = MockConfigEntry(domain="ev_charge_manager", data=config)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    c = entry.runtime_data
    freezer.move_to(dt_util.utcnow() + timedelta(minutes=1))
    hass.states.async_set("sensor.car_power", "6", {"unit_of_measurement": "kW"})
    await c.async_refresh()
    assert c.sites["home"].history["car"].energy_kwh == pytest.approx(0.1)
    entity = hass.states.get("sensor.car_home_measured_charging_energy")
    assert float(entity.state) == pytest.approx(0.1)
    cost = hass.states.get("sensor.car_home_measured_priced_charging_cost")
    assert cost.attributes["cost_coverage"] == "partial"
    assert cost.attributes["unpriced_energy_kwh"] == pytest.approx(0.1)
    assert await hass.config_entries.async_unload(entry.entry_id)
    freezer.move_to(dt_util.utcnow() + timedelta(hours=1))
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.sites["home"].history["car"].energy_kwh == pytest.approx(0.1)
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_distance_counted_once_across_sites_and_provider_changes(hass):
    config = model(hass, brain=False)
    config["sites"].append(
        {**config["sites"][0], "id": "work", "name": "Work", "zone_state": "work"}
    )
    provider = register_provider(hass, {"odometer": "sensor.odometer"}, "odometer")
    config["vehicles"][0]["providers"].append(provider)
    fallback = register_provider(hass, {"odometer": "sensor.fallback_odometer"}, "fallback")
    config["vehicles"][0]["providers"].append(fallback)
    eid = provider["fields"]["odometer"]
    hass.states.async_set(eid, "100", {"unit_of_measurement": "km"})
    entry = MockConfigEntry(domain="ev_charge_manager", data=config)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    c = entry.runtime_data
    hass.states.async_set(eid, "110", {"unit_of_measurement": "km"})
    await c.async_refresh()
    assert c.distance_history["car"].distance_km == 10
    from homeassistant.helpers import entity_registry as er

    er.async_get(hass).async_update_entity(eid, new_entity_id="sensor.renamed_odometer")
    hass.states.async_set("sensor.renamed_odometer", "111", {"unit_of_measurement": "km"})
    await hass.async_block_till_done()
    await c.async_refresh()
    assert c.distance_history["car"].distance_km == 11
    assert float(hass.states.get("sensor.car_measured_driven_distance").state) == 11
    hass.states.async_set("sensor.renamed_odometer", "unknown")
    hass.states.async_set(fallback["fields"]["odometer"], "5000", {"unit_of_measurement": "km"})
    await c.async_refresh()
    assert c.distance_history["car"].distance_km == 11  # Provider calibration jump is not travel.
    hass.states.async_set(fallback["fields"]["odometer"], "5001", {"unit_of_measurement": "km"})
    await c.async_refresh()
    assert c.distance_history["car"].distance_km == 12
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_guest_authority_persists_days_without_optimizer_takeover(hass, freezer):
    config = model(hass)
    hass.states.async_set("sensor.car_cable", "off")
    entry = MockConfigEntry(domain="ev_charge_manager", data=config)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    c = entry.runtime_data
    sid = c.sessions.items["charger"].id
    await hass.services.async_call(
        "ev_charge_manager",
        "simulate_guest_authorization",
        {"charger": "charger", "session_id": sid},
        blocking=True,
        return_response=True,
    )
    for _ in range(3):
        freezer.move_to(dt_util.utcnow() + timedelta(days=1))
        hass.states.async_set("sensor.charger", "completed")
        await c.async_refresh()
        assert c.sessions.items["charger"].authorized and c.sessions.items["charger"].id == sid
    result = await hass.services.async_call(
        "ev_charge_manager",
        "simulate_command",
        {
            "charger": "charger",
            "session_id": sid,
            "key": "guest_stop",
            "owner": "optimizer",
            "action": "stop",
        },
        blocking=True,
        return_response=True,
    )
    assert result["result"] == "guest_protected"
    hass.states.async_set("sensor.charger", "disconnected")
    await c.async_refresh()
    assert "charger" not in c.sessions.items
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_established_brain_session_cannot_move_price_site_on_gps_change(hass):
    config = model(hass)
    config["sites"].append(
        {**config["sites"][0], "id": "work", "name": "Work", "zone_state": "work"}
    )
    entry = MockConfigEntry(domain="ev_charge_manager", data=config)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    c = entry.runtime_data
    sid = c.sessions.items["charger"].id
    hass.states.async_set("sensor.car_tracker", "work")
    await c.async_refresh()
    assert c.sessions.items["charger"].id == sid
    assert c.data["assignments"]["charger"]["car"] == "car"
    assert "car" not in c.data["forecasts"]["work"]
    assert not c.data["forecasts"]["home"]["car"].valid
    result = await hass.services.async_call(
        "ev_charge_manager",
        "simulate_command",
        {
            "charger": "charger",
            "session_id": sid,
            "key": "wrong_site",
            "owner": "optimizer",
            "action": "start",
        },
        blocking=True,
        return_response=True,
    )
    assert result["result"] == "unsafe_session"
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_measurement_does_not_require_soc_or_gps_after_known_association(hass, freezer):
    config = model(hass)
    hass.states.async_set("sensor.car_charging", "on")
    hass.states.async_set("sensor.car_power", "6", {"unit_of_measurement": "kW"})
    entry = MockConfigEntry(domain="ev_charge_manager", data=config)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    c = entry.runtime_data
    hass.states.async_remove("sensor.car_soc")
    hass.states.async_set("sensor.car_tracker", "unknown")
    freezer.move_to(dt_util.utcnow() + timedelta(minutes=1))
    hass.states.async_set("sensor.car_power", "6", {"unit_of_measurement": "kW"})
    await c.async_refresh()
    assert c.data["assignments"]["charger"]["valid"]
    assert not c.data["forecasts"]["home"]["car"].valid
    assert c.sites["home"].history["car"].energy_kwh == pytest.approx(0.1)
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_watchdog_reads_do_not_invent_new_power_measurements(hass, freezer):
    config = model(hass)
    hass.states.async_set("sensor.car_charging", "on")
    hass.states.async_set("sensor.car_power", "6", {"unit_of_measurement": "kW"})
    entry = MockConfigEntry(domain="ev_charge_manager", data=config)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    c = entry.runtime_data
    freezer.move_to(dt_util.utcnow() + timedelta(minutes=1))
    await c.async_refresh()
    assert c.sites["home"].history["car"].energy_kwh == 0
    freezer.move_to(dt_util.utcnow() + timedelta(minutes=4))
    hass.states.async_set("sensor.car_power", "6", {"unit_of_measurement": "kW"})
    hass.states.async_set("sensor.car_charging", "on")
    hass.states.async_set("sensor.car_cable", "on")
    await c.async_refresh()
    assert c.sites["home"].history["car"].energy_kwh == 0  # Source gap exceeds 180 s.
    assert await hass.config_entries.async_unload(entry.entry_id)


def test_negative_final_price_cost_is_credit_not_counter_reset():
    from custom_components.ev_charge_manager.planner import PriceSlot

    now = dt_util.utcnow()
    prices = [PriceSlot(now, now + timedelta(minutes=15), -1)]
    h = History()
    h.sample_power(now, 6, True, prices)
    h.sample_power(now + timedelta(minutes=1), 6, True, prices)
    assert h.energy_kwh == pytest.approx(0.1)
    assert h.cost == pytest.approx(-0.1) and h.unpriced_energy_kwh == 0
    assert History(**h.persistent()).cost == h.cost


async def test_optimizer_start_requires_current_proposed_allocation(hass):
    config = model(hass)
    hass.states.async_set("sensor.car_target", "60")
    entry = MockConfigEntry(domain="ev_charge_manager", data=config)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    c = entry.runtime_data
    assert c.data["forecasts"]["home"]["car"].status == "no_charge_required"
    result = await hass.services.async_call(
        "ev_charge_manager",
        "simulate_command",
        {
            "charger": "charger",
            "session_id": c.sessions.items["charger"].id,
            "key": "no_window",
            "owner": "optimizer",
            "action": "start",
        },
        blocking=True,
        return_response=True,
    )
    assert result["result"] == "unsafe_session"
    assert c.commands.estimated_requests == 0
    assert await hass.config_entries.async_unload(entry.entry_id)
