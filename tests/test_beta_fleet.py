"""Native lifecycle at fleet scale, explicit price sites and safe reconfiguration."""

from copy import deepcopy
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ev_charge_manager.config_flow import defaults
from custom_components.ev_charge_manager.history import History

from .test_manager import register_provider
from .test_price_consumer import NOW, api_result, response


@pytest.mark.parametrize("count", [0, 1, 2, 6])
async def test_simultaneous_multi_site_fleet_and_remove_active_device(hass, freezer, count):
    freezer.move_to(NOW)
    config = defaults()
    producer = MockConfigEntry(domain="ha_energy_price_engine", data={"id": "prices"})
    producer.add_to_hass(hass)
    producer.mock_state(hass, ConfigEntryState.LOADED)
    for i in range(count):
        fields = {
            role: f"sensor.car_{i}_{role}"
            for role in ["soc", "target", "power", "cable", "charging", "tracker"]
        }
        provider = register_provider(hass, fields, f"provider_{i}")
        for role, value in {
            "soc": "60",
            "target": "65",
            "power": "0",
            "cable": "on",
            "charging": "off",
            "tracker": f"zone_{i}",
        }.items():
            hass.states.async_set(
                fields[role], value, {"unit_of_measurement": "kW"} if role == "power" else {}
            )
        charger_source = register_provider(hass, {"status": f"sensor.charger_{i}"}, f"charger_{i}")
        hass.states.async_set(f"sensor.charger_{i}", "charging")
        config["vehicles"].append(
            {
                "id": f"car_{i}",
                "name": f"Car {i}",
                "capacity_kwh": 75,
                "max_kw": 11,
                "providers": [provider],
            }
        )
        config["chargers"].append(
            {
                "id": f"charger_{i}",
                "name": f"Charger {i}",
                "status": f"sensor.charger_{i}",
                "device": charger_source["device"],
                "zone_state": f"zone_{i}",
            }
        )
        config["sites"].append(
            {
                "id": f"site_{i}",
                "name": f"Site {i}",
                "zone_state": f"zone_{i}",
                "timezone": "Europe/Copenhagen",
                "grid_kw": 7,
                "price_source": "energy_price_engine",
                "producer_entry": producer.entry_id,
                "producer_site": "prices",
            }
        )
    entry = MockConfigEntry(domain="ev_charge_manager", data=config)
    entry.add_to_hass(hass)
    with (
        patch("custom_components.ev_charge_manager.price_consumer.import_module") as module,
        patch("homeassistant.core.ServiceRegistry.async_call", new_callable=AsyncMock) as calls,
    ):
        module.return_value.get_api.return_value.lookup.side_effect = (
            lambda site, start, end, **kw: api_result(response(producer.entry_id, site, start, end))
        )
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        c = entry.runtime_data
        assert len(c.data["sessions"]) == count
        assert sum(row["valid"] for row in c.data["assignments"].values()) == count
        for i in range(count):
            forecasts = c.data["forecasts"][f"site_{i}"]
            assert list(forecasts) == [f"car_{i}"]
            assert forecasts[f"car_{i}"].valid
            assert all(a.kw <= 7 for a in forecasts[f"car_{i}"].allocations)
        assert not c.price_schedule.days
        assert not c.price_engine.records
        calls.assert_not_called()
        if count:
            c.distance_history["car_0"] = History(distance_km=42)
            c.sites["site_0"].history["car_0"] = History(energy_kwh=3, cost=4)
            await c.async_save()
            options = deepcopy(c.config)
            options["chargers"] = options["chargers"][1:]
            options["vehicles"] = options["vehicles"][1:]
            hass.config_entries.async_update_entry(entry, options=options)
            await hass.async_block_till_done()
            c = entry.runtime_data
            assert "charger_0" not in c.sessions.items
            assert c.distance_history["car_0"].distance_km == 42
            assert c.sites["site_0"].history["car_0"].energy_kwh == 3
            assert "car_0" not in c.data["vehicles"]
        assert await hass.config_entries.async_unload(entry.entry_id)
    producer.mock_state(hass, ConfigEntryState.NOT_LOADED)


def test_replaced_physical_charger_cannot_inherit_guest_authority():
    from custom_components.ev_charge_manager.sessions import Sessions

    sessions = Sessions()
    old = sessions.update("one", "charging", source_device="physical_a")
    sessions.authorize_guest("one", old.id)
    replacement = sessions.update("one", "charging", source_device="physical_b")
    assert replacement.id != old.id and not replacement.authorized
    assert sessions.update("one", "complete", source_device="physical_b").id == replacement.id


async def test_native_charger_only_capability_review_does_not_require_vehicle(hass):
    from homeassistant.helpers import entity_registry as er

    config = defaults()
    source = register_provider(hass, {"status": "sensor.easee_status"}, "charger")
    enable = er.async_get(hass).async_get_or_create(
        "switch", "demo", "authorize", device_id=source["device"]
    )
    config["chargers"] = [
        {
            "id": "one",
            "name": "One",
            "device": source["device"],
            "status": source["fields"]["status"],
            "zone_state": "home",
        }
    ]
    entry = MockConfigEntry(domain="ev_charge_manager", data=config)
    entry.add_to_hass(hass)
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    fid = flow["flow_id"]
    await hass.config_entries.options.async_configure(fid, {"next_step_id": "command_mapping"})
    flow = await hass.config_entries.options.async_configure(fid, {"provider": "charger:one"})
    assert flow["step_id"] == "command_fields"
    await hass.config_entries.options.async_configure(fid, {"enable_disable": enable.entity_id})
    await hass.config_entries.options.async_configure(fid, {"next_step_id": "finish"})
    assert entry.options["chargers"][0]["command_entities"]["enable_disable"] == enable.id


async def test_duplicate_exact_tesla_vin_across_provider_devices_fails_closed(hass):
    from homeassistant.helpers import device_registry as dr
    from homeassistant.util import dt as dt_util

    from custom_components.ev_charge_manager.vehicle import VehicleRegistry

    a = register_provider(hass, {"soc": "sensor.custom_vin_soc"}, "custom")
    b = register_provider(hass, {"soc": "sensor.fleet_vin_soc"}, "fleet")
    for provider in (a, b):
        dr.async_get(hass).async_update_device(
            provider["device"], manufacturer="Tesla", serial_number="5YJ3E1EA7KF000001"
        )
        hass.states.async_set(provider["fields"]["soc"], "60")
    vehicles = [{"id": "one", "providers": [a]}, {"id": "two", "providers": [b]}]
    registry = VehicleRegistry(hass, vehicles)
    assert registry.resolve(vehicles[0], "soc", dt_util.utcnow()) is None
    assert registry.resolve(vehicles[1], "soc", dt_util.utcnow()) is None
    vehicles = [{"id": "one", "providers": [a, b]}]
    registry = VehicleRegistry(hass, vehicles)
    assert registry.resolve(vehicles[0], "soc", dt_util.utcnow()).provider == "custom"


async def test_native_duplicate_vin_link_must_use_existing_logical_vehicle(hass):
    from homeassistant.helpers import device_registry as dr

    first = register_provider(hass, {"soc": "sensor.first_soc"}, "custom")
    second = register_provider(hass, {"soc": "sensor.second_soc"}, "fleet")
    for provider in [first, second]:
        dr.async_get(hass).async_update_device(
            provider["device"], manufacturer="Tesla", serial_number="5YJ3E1EA7KF000001"
        )
    config = defaults()
    config["vehicles"] = [
        {"id": "one", "name": "One", "providers": [first]},
        {"id": "two", "name": "Two", "providers": []},
    ]
    entry = MockConfigEntry(domain="ev_charge_manager", data=config)
    entry.add_to_hass(hass)
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    fid = flow["flow_id"]
    await hass.config_entries.options.async_configure(fid, {"next_step_id": "provider"})
    await hass.config_entries.options.async_configure(
        fid, {"vehicle": "two", "device": second["device"], "id": "fleet", "primary": True}
    )
    flow = await hass.config_entries.options.async_configure(fid, {"soc": second["fields"]["soc"]})
    assert flow["errors"]["base"] == "duplicate_physical_vehicle"
