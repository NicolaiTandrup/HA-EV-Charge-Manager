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
