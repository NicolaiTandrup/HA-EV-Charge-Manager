"""Renames retain registry identity; device changes never transfer trust."""

from copy import deepcopy

import pytest
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ev_charge_manager.vehicle import VehicleRegistry


@pytest.fixture
def source(hass):
    entry = MockConfigEntry(domain="demo")
    entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={("demo", "car")}
    )
    entity = er.async_get(hass).async_get_or_create("sensor", "demo", "soc", device_id=device.id)
    hass.states.async_set(entity.entity_id, "60")
    vehicle = {
        "id": "logical",
        "providers": [{"id": "custom", "device": device.id, "fields": {"soc": entity.entity_id}}],
    }
    return vehicle, entity


async def test_registry_rename_ignores_reused_old_entity_name(hass, source):
    vehicle, entity = source
    registry = VehicleRegistry(hass, [vehicle])
    assert registry.resolve(vehicle, "soc", dt_util.utcnow()).value == "60"
    er.async_get(hass).async_update_entity(entity.entity_id, new_entity_id="sensor.renamed_soc")
    hass.states.async_set("sensor.renamed_soc", "61")
    hass.states.async_set(entity.entity_id, "99")
    value = registry.resolve(vehicle, "soc", dt_util.utcnow())
    assert value.entity_id == "sensor.renamed_soc" and value.value == "61"
    assert vehicle["id"] == "logical"


async def test_registry_ownership_change_and_disabled_entity_fail_closed(hass, source):
    vehicle, entity = source
    registry = VehicleRegistry(hass, [vehicle])
    registry.resolve(vehicle, "soc", dt_util.utcnow())
    er.async_get(hass).async_update_entity(entity.entity_id, device_id=None)
    assert registry.resolve(vehicle, "soc", dt_util.utcnow()) is None


async def test_deleted_registry_identity_cannot_rebind_by_old_name(hass, source):
    vehicle, entity = source
    registry = VehicleRegistry(hass, [vehicle])
    registry.resolve(vehicle, "soc", dt_util.utcnow())
    er.async_get(hass).async_remove(entity.entity_id)
    er.async_get(hass).async_get_or_create(
        "sensor",
        "demo",
        "imposter",
        suggested_object_id=entity.entity_id.split(".")[1],
        device_id=vehicle["providers"][0]["device"],
    )
    assert registry.resolve(vehicle, "soc", dt_util.utcnow()) is None


async def test_registry_binding_survives_offline_rename(hass, source):
    vehicle, entity = source
    registry = VehicleRegistry(hass, [vehicle])
    registry.resolve(vehicle, "soc", dt_util.utcnow())
    saved = deepcopy(vehicle)
    er.async_get(hass).async_update_entity(entity.entity_id, new_entity_id="sensor.offline_renamed")
    hass.states.async_set("sensor.offline_renamed", "62")
    restored = VehicleRegistry(hass, [saved])
    assert restored.resolve(saved, "soc", dt_util.utcnow()).value == "62"


async def test_rename_persists_reference_without_reloading_physical_session(hass):
    from homeassistant.core import CoreState

    from .test_manager import model

    hass.set_state(CoreState.running)
    entry = MockConfigEntry(domain="ev_charge_manager", data=model(hass))
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    c = entry.runtime_data
    sid = c.sessions.items["charger"].id
    bound = entry.data["vehicles"][0]["providers"][0]["entity_refs"]["soc"]
    er.async_get(hass).async_update_entity("sensor.car_soc", new_entity_id="sensor.renamed_battery")
    hass.states.async_set("sensor.renamed_battery", "62")
    await hass.async_block_till_done()
    await c.async_refresh()
    assert entry.runtime_data is c
    assert c.sessions.items["charger"].id == sid
    provider = entry.data["vehicles"][0]["providers"][0]
    assert provider["fields"]["soc"] == "sensor.renamed_battery"
    assert provider["entity_refs"]["soc"] == bound
    assert c.data["vehicles"]["car"]["soc"].value == "62"
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.data["vehicles"]["car"]["soc"].value == "62"
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_disabled_source_and_unregistered_legacy_mapping_fail_closed(hass, source):
    vehicle, entity = source
    registry = VehicleRegistry(hass, [vehicle])
    er.async_get(hass).async_update_entity(
        entity.entity_id, disabled_by=er.RegistryEntryDisabler.USER
    )
    assert registry.resolve(vehicle, "soc", dt_util.utcnow()) is None
    other = {
        "id": "unbound",
        "providers": [
            {
                "id": "raw",
                "device": vehicle["providers"][0]["device"],
                "fields": {"soc": "sensor.unregistered"},
            }
        ],
    }
    hass.states.async_set("sensor.unregistered", "99")
    assert VehicleRegistry(hass, [other]).resolve(other, "soc", dt_util.utcnow()) is None


async def test_ev_output_cannot_perpetuate_its_own_vehicle_source(hass, source):
    vehicle, entity = source
    output = er.async_get(hass).async_get_or_create(
        "sensor", "ev_charge_manager", "derived_soc", device_id=vehicle["providers"][0]["device"]
    )
    hass.states.async_set(output.entity_id, "60")
    vehicle["providers"][0]["fields"]["soc"] = output.entity_id
    assert VehicleRegistry(hass, [vehicle]).resolve(vehicle, "soc", dt_util.utcnow()) is None
