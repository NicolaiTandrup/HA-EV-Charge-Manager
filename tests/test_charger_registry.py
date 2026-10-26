"""Charger identity survives registry rename and rejects physical reassignment."""

from homeassistant.helpers import entity_registry as er

from custom_components.ev_charge_manager.chargers import ChargerRegistry, discover_status

from .test_manager import register_provider


async def test_stable_charger_source_and_fail_closed_ownership(hass):
    source = register_provider(hass, {"status": "sensor.charger_status"}, "charger")
    charger = {"id": "one", "device": source["device"], "status": source["fields"]["status"]}
    registry = ChargerRegistry(hass, [charger])
    identity = charger["status_ref"]
    er.async_get(hass).async_update_entity(
        charger["status"], translation_key="status", new_entity_id="sensor.renamed"
    )
    assert registry.reconcile()
    assert charger["status_ref"] == identity and registry.source(charger) == "sensor.renamed"
    assert discover_status(hass, source["device"]) == "sensor.renamed"
    er.async_get(hass).async_update_entity("sensor.renamed", device_id=None)
    assert registry.source(charger) is None
    er.async_get(hass).async_remove("sensor.renamed")
    er.async_get(hass).async_get_or_create(
        "sensor", "demo", "recreated", device_id=source["device"], suggested_object_id="renamed"
    )
    assert registry.source(charger) is None  # Never steal a new registry entry.


async def test_duplicate_charger_identity_fails_closed_even_for_imported_options(hass):
    source = register_provider(hass, {"status": "sensor.charger_status"}, "charger")
    chargers = [
        {"id": key, "device": source["device"], "status": source["fields"]["status"]}
        for key in ["one", "two"]
    ]
    registry = ChargerRegistry(hass, chargers)
    assert all(registry.source(c) is None for c in chargers)


async def test_native_discovery_review_and_runtime_rename(hass):
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from .test_manager import model

    config = model(hass)
    config["chargers"] = []
    source = register_provider(hass, {"status": "sensor.discovered_status"}, "charger")
    er.async_get(hass).async_update_entity(source["fields"]["status"], translation_key="status")
    hass.states.async_set(source["fields"]["status"], "charging")
    entry = MockConfigEntry(domain="ev_charge_manager", data=config)
    entry.add_to_hass(hass)
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    fid = flow["flow_id"]
    await hass.config_entries.options.async_configure(fid, {"next_step_id": "discover_charger"})
    flow = await hass.config_entries.options.async_configure(fid, {"device": source["device"]})
    assert flow["step_id"] == "charger"
    assert {
        str(k): k.default() for k in flow["data_schema"].schema if str(k) in {"device", "status"}
    } == {"device": source["device"], "status": source["fields"]["status"]}
    await hass.config_entries.options.async_configure(
        fid,
        {
            "id": "discovered",
            "name": "Charger",
            "device": source["device"],
            "status": source["fields"]["status"],
            "zone_state": "home",
        },
    )
    await hass.config_entries.options.async_configure(fid, {"next_step_id": "finish"})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    c = entry.runtime_data
    identity = c.config["chargers"][0]["status_ref"]
    assert c.data["assignments"]["discovered"]["valid"]
    er.async_get(hass).async_update_entity(
        source["fields"]["status"], new_entity_id="sensor.new_charger_name"
    )
    await hass.async_block_till_done()
    hass.states.async_set("sensor.new_charger_name", "charging")
    await hass.async_block_till_done()
    await c.async_refresh()
    assert c.config["chargers"][0]["status"] == "sensor.new_charger_name"
    assert c.config["chargers"][0]["status_ref"] == identity
    assert c.data["assignments"]["discovered"]["valid"]
    er.async_get(hass).async_update_entity("sensor.new_charger_name", device_id=None)
    await hass.async_block_till_done()
    await c.async_refresh()
    assert not c.data["assignments"]["discovered"]["valid"]
    assert await hass.config_entries.async_unload(entry.entry_id)
