"""Useful native entities remain observations and reflect journal inhibition."""

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ev_charge_manager.sensor import ChargerSensor, ManagerSensor

from .test_manager import model


async def test_charger_power_and_disabled_journal_entities(hass):
    config = model(hass)
    entry = MockConfigEntry(domain="ev_charge_manager", data=config)
    entry.add_to_hass(hass)
    hass.states.async_set("sensor.car_power", "3000", {"unit_of_measurement": "W"})
    assert await hass.config_entries.async_setup(entry.entry_id)
    c = entry.runtime_data
    power = ManagerSensor(c, "charging_power", vehicle="car")
    assert power.available and power.native_value == 3
    status = ChargerSensor(c, config["chargers"][0], "status")
    assert status.available and status.native_value == "charging"
    association = ChargerSensor(c, config["chargers"][0], "association")
    assert association.native_value == "Car"
    journal = ManagerSensor(c, "command_status")
    assert journal.native_value == "disabled"
    c.executor.journal_error = "Unable to verify command journal"
    assert journal.native_value == "blocked"
    assert c.executor.transport is None
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_target_and_plan_observations_do_not_create_control(hass):
    from datetime import timedelta

    from custom_components.ev_charge_manager.planner import Allocation, Forecast
    from custom_components.ev_charge_manager.vehicle import FieldValue

    entry = MockConfigEntry(domain="ev_charge_manager", data=model(hass))
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    c = entry.runtime_data
    now = c.data["updated_at"]
    target = ManagerSensor(c, "charge_target", vehicle="car")
    c.data["vehicles"]["car"]["target"] = FieldValue("0", "number.limit", "custom", now, {})
    assert target.available and target.native_value == 0
    c.data["vehicles"]["car"]["target"] = None
    assert not target.available and target.native_value is None
    f = Forecast(valid=True, status="ready", updated_at=now)
    c.data["forecasts"] = {"test": {"car": f}}
    action = ManagerSensor(c, "next_proposed_action", "test", "car")
    deadline = ManagerSensor(c, "next_deadline", "test", "car")
    assert action.native_value == "no_charge_required" and not deadline.available
    f.stages = [{"deadline": (now + timedelta(hours=4)).isoformat()}]
    assert deadline.available and deadline.native_value == now + timedelta(hours=4)
    f.allocations = [Allocation(now + timedelta(minutes=15), now + timedelta(minutes=30), 1, 1)]
    assert action.native_value == "wait_for_planned_slot"
    f.allocations = [Allocation(now - timedelta(minutes=1), now + timedelta(minutes=10), 1, 1)]
    assert action.native_value == "proposed_charge_now"
    f.valid = False
    assert action.native_value == "blocked"
    assert c.executor.transport is None and c.executor.requests == 0
    assert await hass.config_entries.async_unload(entry.entry_id)
