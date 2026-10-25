"""Versioned registry semantics, never names or arbitrary suffix guesses."""

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ev_charge_manager.chargers import discover_status
from custom_components.ev_charge_manager.executor import capabilities
from custom_components.ev_charge_manager.vehicle import discover


def device(hass, domain):
    entry = MockConfigEntry(domain=domain)
    entry.add_to_hass(hass)
    return dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(domain, "5YJ3E1EA7KF000001")}
    )


async def test_fleet_current_location_and_charge_capabilities(hass):
    d = device(hass, "tesla_fleet")
    registry = er.async_get(hass)
    rows = {}
    for field, domain, key in [
        ("soc", "sensor", "charge_state_battery_level"),
        ("target", "number", "charge_state_charge_limit_soc"),
        ("cable", "binary_sensor", "charge_state_conn_charge_cable"),
        ("power", "sensor", "charge_state_charger_power"),
        ("charging", "switch", "charge_state_charging_state"),
        ("tracker", "device_tracker", "location"),
        ("destination", "device_tracker", "route"),
    ]:
        rows[field] = registry.async_get_or_create(
            domain, "tesla_fleet", "5YJ3E1EA7KF000001-" + key, device_id=d.id, translation_key=key
        ).entity_id
    assert discover(hass, d.id) == {k: v for k, v in rows.items() if k != "destination"}
    hass.services.async_register("switch", "turn_on", lambda call: None)
    assert (
        capabilities(hass, {"id": "fleet", "device": d.id})["start"].registry_id
        == registry.async_get(rows["charging"]).id
    )


async def test_custom_exact_unique_id_contract_and_easee_status(hass):
    d = device(hass, "tesla_custom")
    registry = er.async_get(hass)
    battery = registry.async_get_or_create(
        "sensor", "tesla_custom", "5yj3e1ea7kf000001_battery", device_id=d.id
    )
    location = registry.async_get_or_create(
        "device_tracker", "tesla_custom", "5yj3e1ea7kf000001_location_tracker", device_id=d.id
    )
    registry.async_get_or_create(
        "device_tracker",
        "tesla_custom",
        "5yj3e1ea7kf000001_destination_location_tracker",
        device_id=d.id,
    )
    assert discover(hass, d.id) == {"soc": battery.entity_id, "tracker": location.entity_id}
    c = device(hass, "easee")
    status = registry.async_get_or_create(
        "sensor", "easee", "synthetic_status", device_id=c.id, translation_key="easee_status"
    )
    assert discover_status(hass, c.id) == status.entity_id


async def test_profiles_do_not_guess_from_names_or_ambiguous_semantics(hass):
    d = device(hass, "tesla_custom")
    registry = er.async_get(hass)
    registry.async_get_or_create(
        "sensor", "tesla_custom", "something_battery", device_id=d.id, original_name="Battery"
    )
    assert discover(hass, d.id) == {}
    registry.async_get_or_create(
        "sensor", "tesla_custom", "5yj3e1ea7kf000001_battery", device_id=d.id
    )
    registry.async_get_or_create(
        "sensor", "tesla_custom", "5yj3e1ea7kf000002_battery", device_id=d.id
    )
    assert "soc" not in discover(hass, d.id)


async def test_fleet_sensor_and_switch_share_key_but_boolean_wins(hass):
    d = device(hass, "tesla_fleet")
    registry = er.async_get(hass)
    registry.async_get_or_create(
        "sensor",
        "tesla_fleet",
        "charging_enum",
        device_id=d.id,
        translation_key="charge_state_charging_state",
    )
    switch = registry.async_get_or_create(
        "switch",
        "tesla_fleet",
        "charging_switch",
        device_id=d.id,
        translation_key="charge_state_charging_state",
    )
    assert discover(hass, d.id)["charging"] == switch.entity_id


async def test_native_command_only_provider_can_be_added_without_read_fields(hass):
    from custom_components.ev_charge_manager.config_flow import defaults

    d = device(hass, "tesla_fleet")
    config = defaults()
    config["vehicles"] = [{"id": "car", "name": "Car", "providers": []}]
    entry = MockConfigEntry(domain="ev_charge_manager", data=config)
    entry.add_to_hass(hass)
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    fid = flow["flow_id"]
    await hass.config_entries.options.async_configure(fid, {"next_step_id": "provider"})
    await hass.config_entries.options.async_configure(
        fid, {"vehicle": "car", "device": d.id, "id": "write_only", "primary": False}
    )
    flow = await hass.config_entries.options.async_configure(fid, {})
    assert flow["type"] == "menu"
    await hass.config_entries.options.async_configure(fid, {"next_step_id": "finish"})
    assert entry.options["vehicles"][0]["providers"][0]["fields"] == {}
