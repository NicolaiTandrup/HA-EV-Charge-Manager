"""Exercise the real HA lifecycle and shared boundaries without physical commands."""

from datetime import timedelta
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import CoreState, SupportsResponse
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.ev_charge_manager.command import CommandManager, Intent
from custom_components.ev_charge_manager.config_flow import defaults
from custom_components.ev_charge_manager.diagnostics import async_get_config_entry_diagnostics
from custom_components.ev_charge_manager.prices import OfficialPrices, all_in
from custom_components.ev_charge_manager.sessions import Sessions
from custom_components.ev_charge_manager.vehicle import VehicleRegistry, discover


def register_provider(hass, fields, label="custom"):
    entry = MockConfigEntry(domain="demo", title=label)
    entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={("demo", entry.entry_id)}
    )
    mapped = {}
    for field, eid in fields.items():
        old = hass.states.get(eid)
        domain, obj = eid.split(".")
        entity = er.async_get(hass).async_get_or_create(
            domain, "demo", eid, suggested_object_id=obj, device_id=device.id
        )
        mapped[field] = entity.entity_id
        if old:
            hass.states.async_set(entity.entity_id, old.state, dict(old.attributes))
    return {"id": label, "device": device.id, "fields": mapped}


def model(hass, brain=True, optimizer=True):
    now = dt_util.utcnow()
    now = now.replace(minute=(now.minute // 15) * 15, second=0, microsecond=0)
    values = {
        "soc": "60",
        "target": "65",
        "cable": "on",
        "tracker": "home",
        "charging": "off",
        "power": "0",
    }
    fields = {field: f"sensor.car_{field}" for field in values}
    provider = register_provider(hass, fields)
    fields = provider["fields"]
    for field, value in values.items():
        eid = fields[field]
        fields[field] = eid
        hass.states.async_set(eid, value, {"unit_of_measurement": "kW"} if field == "power" else {})
    hass.states.async_set("sensor.charger", "charging")
    hass.states.async_set(
        "sensor.prices",
        "1",
        {
            "slots": [
                {
                    "start": now.isoformat(),
                    "end": (now + timedelta(hours=24)).isoformat(),
                    "price": 1,
                }
            ]
        },
    )
    return {
        **defaults(),
        "brain_enabled": brain,
        "optimizer_enabled": optimizer,
        "vehicles": [
            {
                "id": "car",
                "name": "Car",
                "capacity_kwh": 75,
                "max_kw": 11,
                "providers": [provider],
            }
        ],
        "chargers": [
            {"id": "charger", "name": "Charger", "status": "sensor.charger", "zone_state": "home"}
        ],
        "sites": [
            {
                "id": "home",
                "name": "Home",
                "timezone": "Europe/Copenhagen",
                "zone_state": "home",
                "grid_kw": 11,
                "price_entity": "sensor.prices",
                "price_attribute": "slots",
                "tariff": {"mode": "all_in"},
            }
        ],
    }


@pytest.mark.parametrize(
    "brain,optimizer", [(True, True), (False, True), (True, False), (False, False)]
)
async def test_lifecycle_and_independent_modules(hass, brain, optimizer):
    hass.set_state(CoreState.running)
    config = model(hass, brain, optimizer)
    entry = MockConfigEntry(domain="ev_charge_manager", data=config)
    entry.add_to_hass(hass)
    with patch("homeassistant.core.ServiceRegistry.async_call", new_callable=AsyncMock) as calls:
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        c = entry.runtime_data
        assert bool(c.sites) == optimizer
        assert bool(c.data["assignments"]) == brain
        if optimizer:
            assert c.data["forecasts"]["home"]["car"].valid
        hass.states.async_set("sensor.car_soc", "61")
        await hass.async_block_till_done()
        diagnostics = await async_get_config_entry_diagnostics(hass, entry)
        assert "sensor.car" not in str(diagnostics)
        calls.assert_not_called()
        assert await hass.config_entries.async_unload(entry.entry_id)


async def test_fallback_is_per_field_and_fresh_primary_off_wins(hass):
    config = model(hass)
    v = config["vehicles"][0]
    hass.states.async_set("sensor.fallback_soc", "70")
    hass.states.async_set("sensor.fallback_cable", "on")
    v["providers"].append(
        register_provider(
            hass, {"soc": "sensor.fallback_soc", "cable": "sensor.fallback_cable"}, "fleet"
        )
    )
    hass.states.async_set("sensor.car_soc", "nan")
    hass.states.async_set("sensor.car_cable", "off")
    reg = VehicleRegistry(hass, [v])
    now = dt_util.utcnow()
    assert reg.resolve(v, "soc", now).provider == "fleet"
    assert reg.resolve(v, "cable", now).value == "off"
    assert reg.resolve(v, "soc", now + timedelta(seconds=901)) is None


def test_durable_guest_session_and_restart_reconciliation():
    s = Sessions()
    a = s.update("charger", "charging")
    s.authorize_guest("charger", a.id)
    assert s.update("charger", "awaiting_start").authorized
    assert s.update("charger", "unavailable") is None
    restored = Sessions(s.persistent())
    assert restored.update("charger", "charging").id == a.id
    assert not restored.items["charger"].authorized
    s.update("charger", "disconnected")
    assert s.update("charger", "charging").id != a.id
    with pytest.raises(ValueError):
        s.authorize_guest("charger", a.id)


def test_command_guards_deduplicate_budget_and_guests():
    c = CommandManager(1)
    a = Intent("1", "session", "optimizer", "start")
    kw = dict(current_session="session", fresh=True, authorized=True)
    assert c.propose(a, **kw, guest=True) == "guest_protected"
    assert c.propose(a, **kw) == "simulated"
    assert c.propose(a, **kw) == "duplicate"
    assert c.propose(Intent("2", "session", "optimizer", "stop"), **kw) == "budget_exhausted"
    assert c.propose(Intent("3", "session", "brain", "probe"), **kw) == "ownership_conflict"
    assert c.propose(a, current_session="new", fresh=True, authorized=True) == "unsafe_session"


async def test_official_nordpool_cache_unit_conversion_and_tariff(hass):
    now = dt_util.utcnow()
    calls = []

    async def prices(call):
        calls.append(call.data)
        if len(calls) == 2:
            return {"DK2": []}
        return {
            "DK2": [
                {
                    "start": now.isoformat(),
                    "end": (now + timedelta(hours=1)).isoformat(),
                    "price": 1000,
                }
            ]
        }

    hass.services.async_register(
        "nordpool", "get_prices_for_date", prices, supports_response=SupportsResponse.ONLY
    )
    client = OfficialPrices(hass)
    site = {
        "nordpool_entry": "np",
        "timezone": "Europe/Copenhagen",
        "tariff": {"mode": "spot_ex_vat", "grid": 0.2, "tax": 0.3, "supplier": 0.1, "vat": 0.25},
    }
    slots = await client.get(site, now)
    assert len(slots) == 4 and slots[0].price == pytest.approx(2)
    await client.get(site, now)
    assert len(calls) == 2
    assert calls[0]["currency"] == "DKK"
    with pytest.raises(ValueError):
        all_in(slots, {"mode": "all_in", "vat": 0.25})


async def test_semantic_discovery_ignores_names_and_ambiguity(hass):
    source = MockConfigEntry(domain="demo")
    source.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=source.entry_id, identifiers={("demo", "car")}
    )
    reg = er.async_get(hass)
    e = reg.async_get_or_create(
        "sensor", "demo", "soc", device_id=device.id, translation_key="battery_level"
    )
    assert discover(hass, device.id)["soc"] == e.entity_id
    reg.async_get_or_create(
        "sensor", "demo", "soc2", device_id=device.id, translation_key="battery_level"
    )
    assert "soc" not in discover(hass, device.id)


async def test_ui_config_and_options(hass):
    result = await hass.config_entries.flow.async_init(
        "ev_charge_manager", context={"source": "user"}
    )
    assert result["type"] == "menu"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "finish"}
    )
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    entry = result["result"]
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == "menu"
    await hass.config_entries.async_unload(entry.entry_id)


async def test_watchdog_expires_and_disconnect_revokes(hass, freezer):
    hass.set_state(CoreState.running)
    entry = MockConfigEntry(domain="ev_charge_manager", data=model(hass))
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.data["assignments"]["charger"]["valid"]
    freezer.move_to(dt_util.utcnow() + timedelta(seconds=916))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert not entry.runtime_data.data["assignments"]["charger"]["valid"]
    hass.states.async_set("sensor.charger", "disconnected")
    await hass.async_block_till_done()
    assert not entry.runtime_data.sessions.items
    assert await hass.config_entries.async_unload(entry.entry_id)


def test_passive_global_unique_mapping_and_ambiguity():
    from custom_components.ev_charge_manager.brain import unique_matching

    assert unique_matching({"one": ["a", "b"], "two": ["b"]}) == {"one": "a", "two": "b"}
    assert unique_matching({"one": ["a", "b"], "two": ["a", "b"]}) == {}
    assert unique_matching({"one": ["a"], "two": ["a"]}) == {}


def test_probe_simulation_commissioning_guest_and_bounded_restore():
    from custom_components.ev_charge_manager.simulation import simulate_probe

    kw = dict(
        charger="one",
        candidates=["a", "b"],
        samples=[{"a": 1, "b": 0}],
        commissioned_vehicles=["a", "b"],
        commissioned_chargers=["one"],
    )
    assert simulate_probe(**kw)["vehicle"] == "a"
    assert simulate_probe(**kw, guest=True)["vehicle"] is None
    kw["commissioned_vehicles"] = ["a"]
    assert simulate_probe(**kw)["reason"] == "not_commissioned_or_guest"
    kw["commissioned_vehicles"] = ["a", "b"]
    kw["samples"] = [{"a": 0, "b": 0}] * 100
    result = simulate_probe(**kw)
    assert result["vehicle"] is None
    assert len(result["trace"]) == 4
    assert result["trace"][-1]["step"] == "simulated_restore"


async def test_guest_service_is_session_bound_and_never_dispatches_hardware(hass):
    config = model(hass)
    hass.states.async_set("sensor.car_cable", "off")
    entry = MockConfigEntry(domain="ev_charge_manager", data=config)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    sid = entry.runtime_data.data["sessions"]["charger"]["session_id"]
    result = await hass.services.async_call(
        "ev_charge_manager",
        "simulate_guest_authorization",
        {"charger": "charger", "session_id": sid},
        blocking=True,
        return_response=True,
    )
    assert result == {"mode": "simulation", "authorized": True, "physical_commands": 0}
    assert entry.runtime_data.sessions.items["charger"].authorized
    hass.states.async_set("sensor.charger", "disconnected")
    await entry.runtime_data.async_refresh()
    from homeassistant.exceptions import ServiceValidationError

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "ev_charge_manager",
            "simulate_guest_authorization",
            {"charger": "charger", "session_id": sid},
            blocking=True,
            return_response=True,
        )
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert not hass.services.has_service("ev_charge_manager", "simulate_guest_authorization")


async def test_two_sites_and_measured_guest_power_constrain_plan(hass):
    config = model(hass, brain=False)
    hass.states.async_set("sensor.guest_power", "6000", {"unit_of_measurement": "W"})
    config["sites"][0]["guest_power_entity"] = "sensor.guest_power"
    config["sites"].append(
        {**config["sites"][0], "id": "work", "name": "Work", "zone_state": "work"}
    )
    entry = MockConfigEntry(domain="ev_charge_manager", data=config)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    c = entry.runtime_data
    home = c.data["forecasts"]["home"]["car"]
    assert home.power_kw == 5
    assert not c.data["forecasts"]["work"]["car"].valid
    assert all(a.kw <= 5 for a in home.allocations)
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_time_varying_grid_tariff_and_no_double_counting(hass):
    from custom_components.ev_charge_manager.adapters import parse_prices

    now = dt_util.utcnow()
    slots = parse_prices(
        {
            "slots": [
                {
                    "start": now.isoformat(),
                    "end": (now + timedelta(hours=1)).isoformat(),
                    "price": 1,
                }
            ]
        }
    )
    from dataclasses import replace

    grid = [replace(s, price=0.2 + i * 0.1) for i, s in enumerate(slots)]
    priced = all_in(slots, {"mode": "spot_ex_vat", "grid_slots": grid, "vat": 0.25})
    assert priced[0].price == pytest.approx(1.5)
    assert priced[-1].price == pytest.approx(1.875)
    with pytest.raises(ValueError):
        all_in(slots, {"mode": "spot_ex_vat", "grid_slots": grid[:1]})


async def test_provider_and_site_ui_validation(hass):
    flow = await hass.config_entries.flow.async_init(
        "ev_charge_manager", context={"source": "user"}
    )
    fid = flow["flow_id"]
    flow = await hass.config_entries.flow.async_configure(fid, {"next_step_id": "vehicle"})
    assert flow["type"] == "form"
    flow = await hass.config_entries.flow.async_configure(
        fid, {"name": "Car", "capacity_kwh": 75, "max_kw": 11, "efficiency": 0.9}
    )
    assert flow["type"] == "menu"
    flow = await hass.config_entries.flow.async_configure(fid, {"next_step_id": "site"})
    assert flow["type"] == "form"
    data = {
        "id": "home",
        "name": "Home",
        "zone_state": "home",
        "timezone": "Europe/Copenhagen",
        "grid_kw": 11,
        "price_entity": "sensor.prices",
        "price_attribute": "slots",
        "price_multiplier": 1,
        "area": "DK2",
        "price_basis": "all_in",
        "grid": 0,
        "tax": 0,
        "supplier": 0,
        "vat": 0.25,
    }
    flow = await hass.config_entries.flow.async_configure(fid, data)
    assert flow["errors"]["base"] == "invalid_mapping"
    data["vat"] = 0
    flow = await hass.config_entries.flow.async_configure(fid, data)
    assert flow["type"] == "menu"
    flow = await hass.config_entries.flow.async_configure(fid, {"next_step_id": "finish"})
    await hass.async_block_till_done()
    assert flow["type"] == "create_entry"
    assert await hass.config_entries.async_unload(flow["result"].entry_id)


async def test_command_service_protects_guest_and_captures_unplug_replug_race(hass):
    hass.set_state(CoreState.running)
    config = model(hass)
    hass.states.async_set("sensor.car_cable", "off")
    entry = MockConfigEntry(domain="ev_charge_manager", data=config)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    c = entry.runtime_data
    sid = c.sessions.items["charger"].id
    await hass.services.async_call(
        "ev_charge_manager",
        "simulate_guest_authorization",
        {"charger": "charger", "session_id": sid},
        blocking=True,
        return_response=True,
    )
    intent = {
        "charger": "charger",
        "session_id": sid,
        "key": "one",
        "owner": "optimizer",
        "action": "stop",
    }
    result = await hass.services.async_call(
        "ev_charge_manager", "simulate_command", intent, blocking=True, return_response=True
    )
    assert result["result"] == "guest_protected"
    hass.states.async_set("sensor.charger", "disconnected")
    # Validate against current physical input even before an event refresh completes.
    result = await hass.services.async_call(
        "ev_charge_manager",
        "simulate_command",
        {**intent, "owner": "manual"},
        blocking=True,
        return_response=True,
    )
    assert result["result"] == "unsafe_session"
    hass.states.async_set("sensor.charger", "charging")
    await hass.async_block_till_done()
    await c.async_refresh()
    assert c.sessions.items["charger"].id != sid
    assert not c.sessions.items["charger"].authorized
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_options_edit_keeps_vehicle_identity_and_provider_links(hass):
    config = model(hass)
    entry = MockConfigEntry(domain="ev_charge_manager", data=config)
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    fid = result["flow_id"]
    result = await hass.config_entries.options.async_configure(fid, {"next_step_id": "edit"})
    result = await hass.config_entries.options.async_configure(fid, {"item": "vehicles:car"})
    assert result["step_id"] == "vehicle"
    result = await hass.config_entries.options.async_configure(
        fid, {"name": "Renamed", "capacity_kwh": 80, "max_kw": 7, "efficiency": 0.9}
    )
    result = await hass.config_entries.options.async_configure(fid, {"next_step_id": "finish"})
    assert result["type"] == "create_entry"
    vehicle = entry.options["vehicles"][0]
    assert vehicle["id"] == "car"
    assert vehicle["providers"] == config["vehicles"][0]["providers"]
    assert vehicle["name"] == "Renamed"


async def test_official_prices_failures_are_rate_limited(hass):
    from homeassistant.exceptions import HomeAssistantError

    calls = []

    async def failure(call):
        calls.append(call.data)
        raise HomeAssistantError("Temporarily unavailable")

    hass.services.async_register(
        "nordpool", "get_prices_for_date", failure, supports_response=SupportsResponse.ONLY
    )
    client = OfficialPrices(hass)
    site = {
        "nordpool_entry": "np",
        "timezone": "Europe/Copenhagen",
        "tariff": {"mode": "spot_ex_vat"},
    }
    now = dt_util.utcnow()
    assert await client.get(site, now) == []
    assert await client.get(site, now + timedelta(seconds=15)) == []
    assert len(calls) == 2
    await client.get(site, now + timedelta(minutes=16))
    assert len(calls) == 4


async def test_shared_provider_ui_attaches_fields_and_rejects_foreign_device(hass):
    source = MockConfigEntry(domain="demo")
    source.add_to_hass(hass)
    devices = dr.async_get(hass)
    device = devices.async_get_or_create(
        config_entry_id=source.entry_id, identifiers={("demo", "provider")}
    )
    foreign = devices.async_get_or_create(
        config_entry_id=source.entry_id, identifiers={("demo", "foreign")}
    )
    reg = er.async_get(hass)
    soc = reg.async_get_or_create(
        "sensor", "demo", "soc", device_id=device.id, translation_key="battery_level"
    )
    bad = reg.async_get_or_create("sensor", "demo", "bad", device_id=foreign.id)
    config = {
        **defaults(),
        "vehicles": [
            {"id": "car", "name": "Car", "capacity_kwh": 75, "max_kw": 11, "providers": []}
        ],
    }
    entry = MockConfigEntry(domain="ev_charge_manager", data=config)
    entry.add_to_hass(hass)
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    fid = flow["flow_id"]
    await hass.config_entries.options.async_configure(fid, {"next_step_id": "provider"})
    flow = await hass.config_entries.options.async_configure(
        fid, {"vehicle": "car", "device": device.id, "id": "custom", "primary": True}
    )
    assert flow["step_id"] == "fields"
    flow = await hass.config_entries.options.async_configure(fid, {"soc": bad.entity_id})
    assert flow["errors"]["base"] == "invalid_mapping"
    flow = await hass.config_entries.options.async_configure(fid, {"soc": soc.entity_id})
    assert flow["type"] == "menu"
    await hass.config_entries.options.async_configure(fid, {"next_step_id": "finish"})
    assert entry.options["vehicles"][0]["providers"][0]["fields"] == {"soc": soc.entity_id}
    assert entry.options["vehicles"][0]["id"] == "car"


async def test_official_price_source_runs_through_unified_coordinator(hass):
    now = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
    config = model(hass)
    site = config["sites"][0]
    site.pop("price_entity")
    site.update(nordpool_entry="official", tariff={"mode": "spot_ex_vat", "grid": 0.2, "vat": 0.25})
    count = 0

    async def prices(call):
        nonlocal count
        count += 1
        if count == 2:
            return {"DK2": []}
        return {
            "DK2": [
                {
                    "start": now.isoformat(),
                    "end": (now + timedelta(hours=24)).isoformat(),
                    "price": 1000,
                }
            ]
        }

    hass.services.async_register(
        "nordpool", "get_prices_for_date", prices, supports_response=SupportsResponse.ONLY
    )
    entry = MockConfigEntry(domain="ev_charge_manager", data=config)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    f = entry.runtime_data.data["forecasts"]["home"]["car"]
    assert f.valid and f.allocations
    assert all(a.price == pytest.approx(1.5) for a in f.allocations)
    await entry.runtime_data.async_refresh()
    assert count == 2
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_unknown_guest_demand_is_not_assumed_zero(hass):
    config = model(hass)
    config["chargers"].append(
        {"id": "guest", "name": "Guest", "status": "sensor.guest_status", "zone_state": "home"}
    )
    hass.states.async_set("sensor.guest_status", "disconnected")
    entry = MockConfigEntry(domain="ev_charge_manager", data=config)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    c = entry.runtime_data
    assert c.data["forecasts"]["home"]["car"].valid
    hass.states.async_set("sensor.guest_status", "awaiting_start")
    await c.async_refresh()
    assert not c.data["forecasts"]["home"]["car"].valid
    hass.states.async_set("sensor.guest_status", "unavailable")
    await c.async_refresh()
    assert not c.data["forecasts"]["home"]["car"].valid
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_guest_authorization_reconciles_known_vehicle_source_race(hass):
    config = model(hass)
    hass.states.async_set("sensor.car_cable", "off")
    entry = MockConfigEntry(domain="ev_charge_manager", data=config)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    sid = entry.runtime_data.sessions.items["charger"].id
    hass.states.async_set("sensor.car_cable", "on")
    from homeassistant.exceptions import ServiceValidationError

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "ev_charge_manager",
            "simulate_guest_authorization",
            {"charger": "charger", "session_id": sid},
            blocking=True,
            return_response=True,
        )
    assert entry.runtime_data.sessions.items["charger"].vehicle == "car"
    assert not entry.runtime_data.sessions.items["charger"].authorized
    assert await hass.config_entries.async_unload(entry.entry_id)
