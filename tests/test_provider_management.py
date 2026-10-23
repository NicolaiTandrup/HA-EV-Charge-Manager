"""Provider management retains logical identity, order and ownership checks."""

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .test_manager import model, register_provider


@pytest.mark.parametrize(
    "action,expected",
    [
        ("primary", ["fleet", "custom"]),
        ("up", ["fleet", "custom"]),
        ("down", ["custom", "fleet"]),
        ("remove", ["custom"]),
    ],
)
async def test_provider_management(hass, action, expected):
    config = model(hass)
    config["vehicles"][0]["providers"].append(
        register_provider(hass, {"soc": "sensor.fleet_soc"}, "fleet")
    )
    entry = MockConfigEntry(domain="ev_charge_manager", data=config)
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    fid = result["flow_id"]
    await hass.config_entries.options.async_configure(fid, {"next_step_id": "manage_provider"})
    await hass.config_entries.options.async_configure(fid, {"provider": "car:fleet"})
    result = await hass.config_entries.options.async_configure(fid, {"action": action})
    assert result["type"] == "menu"
    await hass.config_entries.options.async_configure(fid, {"next_step_id": "finish"})
    assert entry.options["vehicles"][0]["id"] == "car"
    assert [p["id"] for p in entry.options["vehicles"][0]["providers"]] == expected


async def test_replacement_requires_reviewed_device_owned_fields(hass):
    config = model(hass)
    replacement = register_provider(hass, {"soc": "sensor.replacement_soc"}, "new")
    entry = MockConfigEntry(domain="ev_charge_manager", data=config)
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    fid = result["flow_id"]
    await hass.config_entries.options.async_configure(fid, {"next_step_id": "manage_provider"})
    await hass.config_entries.options.async_configure(fid, {"provider": "car:custom"})
    await hass.config_entries.options.async_configure(fid, {"action": "replace"})
    await hass.config_entries.options.async_configure(fid, {"device": replacement["device"]})
    result = await hass.config_entries.options.async_configure(fid, {"soc": "sensor.car_soc"})
    assert result["errors"]["base"] == "invalid_mapping"
    result = await hass.config_entries.options.async_configure(
        fid, {"soc": replacement["fields"]["soc"]}
    )
    assert result["type"] == "menu"
    await hass.config_entries.options.async_configure(fid, {"next_step_id": "finish"})
    vehicle = entry.options["vehicles"][0]
    assert vehicle["id"] == "car"
    assert vehicle["providers"][0]["id"] == "custom"
    assert vehicle["providers"][0]["device"] == replacement["device"]
    assert vehicle["providers"][0]["entity_refs"]["soc"]
