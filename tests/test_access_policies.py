"""Native disable/eligibility policy changes never become control permission."""

from copy import deepcopy

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .test_manager import model


async def test_disabled_charger_and_vehicle_are_not_admitted(hass):
    config = model(hass)
    config["chargers"][0]["enabled"] = False
    entry = MockConfigEntry(domain="ev_charge_manager", data=config)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    c = entry.runtime_data
    assert not c.data["assignments"]["charger"]["valid"]
    assert not c.data["forecasts"]["home"]
    assert c.sessions.items["charger"].id  # Physical plug identity still observed.
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_vehicle_charger_eligibility_and_maximum_power(hass):
    config = model(hass)
    config["chargers"][0].update(restrict_vehicles=True, eligible_vehicles=["another"], max_kw=3.7)
    entry = MockConfigEntry(domain="ev_charge_manager", data=config)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    assert not entry.runtime_data.data["assignments"]["charger"]["valid"]
    options = deepcopy(entry.runtime_data.config)
    options["chargers"][0]["eligible_vehicles"] = ["car"]
    hass.config_entries.async_update_entry(entry, options=options)
    await hass.async_block_till_done()
    forecast = entry.runtime_data.data["forecasts"]["home"]["car"]
    assert forecast.valid and all(a.kw <= 3.7 for a in forecast.allocations)
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_native_access_policy_options_preserve_identity(hass):
    entry = MockConfigEntry(domain="ev_charge_manager", data=model(hass))
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    fid = result["flow_id"]
    await hass.config_entries.options.async_configure(fid, {"next_step_id": "access_policy"})
    await hass.config_entries.options.async_configure(fid, {"item": "chargers:charger"})
    result = await hass.config_entries.options.async_configure(
        fid,
        {
            "enabled": False,
            "restrict_vehicles": True,
            "eligible_vehicles": ["car"],
            "guest_policy": "deny",
            "site_id": "home",
            "max_kw": 3.7,
        },
    )
    assert result["type"] == "menu"
    await hass.config_entries.options.async_configure(fid, {"next_step_id": "finish"})
    charger = entry.options["chargers"][0]
    assert charger["id"] == "charger" and not charger["enabled"]
    assert charger["max_kw"] == 3.7 and charger["site_id"] == "home"


async def test_restricted_empty_site_and_disabled_site_suppress_forecasts(hass):
    config = model(hass)
    config["vehicles"][0].update(restrict_sites=True, allowed_sites=[])
    entry = MockConfigEntry(domain="ev_charge_manager", data=config)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    assert not entry.runtime_data.data["forecasts"]["home"]
    options = deepcopy(entry.runtime_data.config)
    options["vehicles"][0]["allowed_sites"] = ["home"]
    options["sites"][0]["enabled"] = False
    hass.config_entries.async_update_entry(entry, options=options)
    await hass.async_block_till_done()
    assert not entry.runtime_data.sites
    assert not entry.runtime_data.data["assignments"]["charger"]["valid"]
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_guest_deny_is_enforced_without_discarding_physical_connection(hass):
    import pytest
    from homeassistant.exceptions import ServiceValidationError

    config = model(hass)
    config["chargers"][0]["guest_policy"] = "deny"
    hass.states.async_set("sensor.car_cable", "off")
    entry = MockConfigEntry(domain="ev_charge_manager", data=config)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    c = entry.runtime_data
    sid = c.sessions.items["charger"].id
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "ev_charge_manager",
            "simulate_guest_authorization",
            {"charger": "charger", "session_id": sid},
            blocking=True,
            return_response=True,
        )
    assert c.sessions.items["charger"].id == sid
    assert not c.sessions.items["charger"].authorized
    assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), 0, "not_a_number"])
async def test_invalid_imported_charger_limit_fails_closed(hass, invalid):
    config = model(hass)
    config["chargers"][0]["max_kw"] = invalid
    entry = MockConfigEntry(domain="ev_charge_manager", data=config)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    assert not entry.runtime_data.data["assignments"]["charger"]["valid"]
    assert not entry.runtime_data.data["forecasts"]["home"]
    assert await hass.config_entries.async_unload(entry.entry_id)
