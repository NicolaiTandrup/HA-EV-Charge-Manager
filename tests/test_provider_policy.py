"""Independent READ/WRITE policies, ordinary native UI and arbitrary fleet size."""

from unittest.mock import patch

import pytest
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ev_charge_manager.vehicle import VehicleRegistry

from .test_manager import model, register_provider


async def test_read_preference_fallback_and_field_override(hass):
    config = model(hass)
    vehicle = config["vehicles"][0]
    provider = register_provider(
        hass, {"soc": "sensor.fleet_soc", "target": "sensor.fleet_target"}, "fleet"
    )
    vehicle["providers"].append(provider)
    hass.states.async_set("sensor.fleet_soc", "82")
    hass.states.async_set("sensor.fleet_target", "90")
    vehicle["provider_policy"] = {
        "read_provider": "fleet",
        "write_provider": "custom",
        "read_fallback": False,
        "write_fallback": False,
        "read_overrides": {"target": "custom"},
    }
    registry = VehicleRegistry(hass, [vehicle])
    now = dt_util.utcnow()
    assert registry.resolve(vehicle, "soc", now).provider == "fleet"
    assert registry.resolve(vehicle, "target", now).provider == "custom"
    hass.states.async_set("sensor.fleet_soc", "unavailable")
    assert registry.resolve(vehicle, "soc", now) is None
    vehicle["provider_policy"]["read_fallback"] = True
    assert registry.resolve(vehicle, "soc", now).provider == "custom"
    vehicle["provider_policy"]["read_provider"] = "deleted"
    assert registry.resolve(vehicle, "soc", now) is None  # Never silently change preference.


async def test_native_policy_options_preserve_vehicle_identity(hass):
    config = model(hass)
    vehicle = config["vehicles"][0]
    vehicle["providers"].append(register_provider(hass, {"soc": "sensor.fleet_soc"}, "fleet"))
    entry = MockConfigEntry(domain="ev_charge_manager", data=config)
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    fid = result["flow_id"]
    await hass.config_entries.options.async_configure(fid, {"next_step_id": "provider_policy"})
    await hass.config_entries.options.async_configure(fid, {"vehicle": "car"})
    result = await hass.config_entries.options.async_configure(
        fid,
        {
            "read_provider": "custom",
            "write_provider": "fleet",
            "read_fallback": True,
            "write_fallback": False,
            "read_soc": "fleet",
            "write_start": "custom",
        },
    )
    assert result["type"] == "menu"
    await hass.config_entries.options.async_configure(fid, {"next_step_id": "finish"})
    policy = entry.options["vehicles"][0]["provider_policy"]
    assert policy["read_overrides"] == {"soc": "fleet"}
    assert policy["write_overrides"] == {"start": "custom"}
    assert policy["write_provider"] == "fleet" and not policy["write_fallback"]
    assert entry.options["vehicles"][0]["id"] == "car"


async def test_charger_device_cannot_have_two_logical_controllers(hass):
    config = model(hass)
    source = register_provider(hass, {"status": "sensor.physical_charger"}, "charger_source")
    charger = {
        "id": "one",
        "name": "One",
        "device": source["device"],
        "status": source["fields"]["status"],
        "zone_state": "home",
    }
    config["chargers"] = [charger]
    entry = MockConfigEntry(domain="ev_charge_manager", data=config)
    entry.add_to_hass(hass)
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    fid = flow["flow_id"]
    await hass.config_entries.options.async_configure(fid, {"next_step_id": "charger"})
    result = await hass.config_entries.options.async_configure(fid, {**charger, "id": "two"})
    assert result["type"] == "form" and result["errors"]["base"] == "invalid_mapping"


@pytest.mark.parametrize("count", [0, 1, 2, 6])
async def test_native_initial_setup_arbitrary_fleet_and_dynamic_options(hass, count):
    from custom_components.ev_charge_manager.config_flow import defaults

    flow = await hass.config_entries.flow.async_init(
        "ev_charge_manager", context={"source": "user"}
    )
    fid = flow["flow_id"]
    for i in range(count):
        await hass.config_entries.flow.async_configure(fid, {"next_step_id": "vehicle"})
        flow = await hass.config_entries.flow.async_configure(
            fid, {"name": f"Vehicle {i}", "capacity_kwh": 70, "max_kw": 11, "efficiency": 0.9}
        )
        assert flow["type"] == "menu"
        source = register_provider(hass, {"status": f"sensor.charger_{i}"}, f"charger_{i}")
        await hass.config_entries.flow.async_configure(fid, {"next_step_id": "charger"})
        flow = await hass.config_entries.flow.async_configure(
            fid,
            {
                "id": f"charger_{i}",
                "name": f"Charger {i}",
                "device": source["device"],
                "status": source["fields"]["status"],
                "zone_state": f"site_{i % 2}",
            },
        )
        assert flow["type"] == "menu"
    with patch("custom_components.ev_charge_manager.async_setup_entry", return_value=True):
        flow = await hass.config_entries.flow.async_configure(fid, {"next_step_id": "finish"})
        await hass.async_block_till_done()
    assert flow["type"] == "create_entry"
    entry = flow["result"]
    assert len(entry.data["vehicles"]) == len(entry.data["chargers"]) == count
    assert len({v["id"] for v in entry.data["vehicles"]}) == count
    assert "commands_enabled" not in entry.data
    if not count:
        assert entry.data == defaults()
        return
    original = entry.data["vehicles"][0]["id"]
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    fid = flow["flow_id"]
    await hass.config_entries.options.async_configure(fid, {"next_step_id": "edit"})
    await hass.config_entries.options.async_configure(fid, {"item": f"vehicles:{original}"})
    await hass.config_entries.options.async_configure(
        fid, {"name": "Renamed", "capacity_kwh": 72, "max_kw": 7, "efficiency": 0.95}
    )
    await hass.config_entries.options.async_configure(fid, {"next_step_id": "remove"})
    await hass.config_entries.options.async_configure(fid, {"item": "chargers:charger_0"})
    await hass.config_entries.options.async_configure(fid, {"next_step_id": "finish"})
    assert entry.options["vehicles"][0]["id"] == original
    assert entry.options["vehicles"][0]["name"] == "Renamed"
    assert len(entry.options["chargers"]) == count - 1
