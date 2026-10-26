"""Reviewed manual identities remain session scoped and simulation only."""

from copy import deepcopy

import pytest
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .test_manager import model, register_provider


def ambiguous(hass):
    config = model(hass)
    second = deepcopy(config["vehicles"][0])
    second.update(id="second", name="Second")
    second["providers"] = [
        register_provider(
            hass, {"cable": "sensor.second_cable", "tracker": "sensor.second_tracker"}, "second"
        )
    ]
    hass.states.async_set("sensor.second_cable", "on")
    hass.states.async_set("sensor.second_tracker", "home")
    config["vehicles"].append(second)
    return config


async def test_reviewed_association_resolves_only_current_physical_session(hass):
    config = ambiguous(hass)
    entry = MockConfigEntry(domain="ev_charge_manager", data=config)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    c = entry.runtime_data
    assert c.data["assignments"]["charger"]["mode"] == "ambiguous"
    sid = c.sessions.items["charger"].id
    response = await hass.services.async_call(
        "ev_charge_manager",
        "simulate_vehicle_association",
        {"charger": "charger", "session_id": sid, "vehicle": "car"},
        blocking=True,
        return_response=True,
    )
    assert response["physical_commands"] == 0
    assert c.data["assignments"]["charger"]["car"] == "car"
    assert c.data["assignments"]["charger"]["mode"] == "manually_assigned"
    hass.states.async_set("sensor.charger", "disconnected")
    await c.async_refresh()
    hass.states.async_set("sensor.charger", "charging")
    await c.async_refresh()
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "ev_charge_manager",
            "simulate_vehicle_association",
            {"charger": "charger", "session_id": sid, "vehicle": "car"},
            blocking=True,
            return_response=True,
        )
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_native_options_review_uses_labels_and_captured_session(hass):
    entry = MockConfigEntry(domain="ev_charge_manager", data=ambiguous(hass))
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    c = entry.runtime_data
    result = await hass.config_entries.options.async_init(entry.entry_id)
    fid = result["flow_id"]
    result = await hass.config_entries.options.async_configure(
        fid, {"next_step_id": "manual_association"}
    )
    assert result["step_id"] == "manual_association"
    result = await hass.config_entries.options.async_configure(
        fid, {"charger": "charger", "vehicle": "car"}
    )
    assert result["type"] == "menu"
    assert c.data["assignments"]["charger"]["mode"] == "manually_assigned"
    assert c.executor.transport is None
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_review_cannot_steal_another_charger_or_guest(hass):
    config = ambiguous(hass)
    config["chargers"].append(
        {"id": "two", "name": "Two", "status": "sensor.two", "zone_state": "home"}
    )
    hass.states.async_set("sensor.two", "charging")
    entry = MockConfigEntry(domain="ev_charge_manager", data=config)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    c = entry.runtime_data
    from custom_components.ev_charge_manager.association import associate

    await associate(c, "charger", c.sessions.items["charger"].id, "car")
    with pytest.raises(ServiceValidationError):
        await associate(c, "two", c.sessions.items["two"].id, "car")
    # Guest authority is a different state from reviewed known identity.
    c.sessions.items["two"].authorized = True
    with pytest.raises(ServiceValidationError):
        await associate(c, "two", c.sessions.items["two"].id, "second")
    assert await hass.config_entries.async_unload(entry.entry_id)
