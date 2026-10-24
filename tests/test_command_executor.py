"""HA service harness only: no external installation or hardware is contacted."""

from unittest.mock import AsyncMock

from homeassistant.helpers import entity_registry as er

from custom_components.ev_charge_manager.executor import (
    CommandContext,
    CommandExecutor,
    capabilities,
)

from .test_manager import register_provider


def setup_target(hass):
    provider = register_provider(hass, {"charging": "switch.charge", "limit": "number.limit"})
    registry = er.async_get(hass)
    registry.async_update_entity("switch.charge", translation_key="charging")
    registry.async_update_entity("number.limit", translation_key="charge_limit")
    hass.states.async_set("switch.charge", "off")
    hass.states.async_set("number.limit", "70", {"min": 50, "max": 100, "step": 1})
    hass.services.async_register("switch", "turn_on", AsyncMock())
    hass.services.async_register("switch", "turn_off", AsyncMock())
    hass.services.async_register("number", "set_value", AsyncMock())
    return provider


def context():
    return CommandContext(
        session_id="plug1",
        current_session="plug1",
        owner="optimizer",
        fresh=True,
        authorized=True,
        commissioned_vehicle=True,
        commissioned_charger=True,
    )


async def test_disabled_by_default_and_success_is_not_confirmation(hass):
    provider = setup_target(hass)
    target = capabilities(hass, provider)["start"]
    assert (await CommandExecutor(hass).execute("a", target, context())).status == "disabled"
    dispatch = AsyncMock()
    executor = CommandExecutor(hass, transport=dispatch)
    result = await executor.execute("a", target, context())
    assert result.status == "awaiting_observation"
    dispatch.assert_awaited_once_with(
        "switch", "turn_on", {"entity_id": "switch.charge"}, blocking=True
    )
    assert (await executor.execute("a", target, context())).status == "awaiting_observation"
    assert dispatch.await_count == 1
    hass.states.async_set("switch.charge", "on")
    assert (await executor.execute("a", target, context())).status == "observed"
    assert dispatch.await_count == 1


async def test_ambiguous_failure_never_retries_or_changes_provider(hass):
    provider = setup_target(hass)
    target = capabilities(hass, provider)["start"]
    dispatch = AsyncMock(side_effect=TimeoutError())
    executor = CommandExecutor(hass, transport=dispatch)
    assert (await executor.execute("a", target, context())).status == "uncertain"
    assert (await executor.execute("a", target, context())).status == "uncertain"
    assert (await executor.execute("b", target, context())).status == "resource_uncertain"
    assert dispatch.await_count == 1


async def test_read_before_write_identity_budget_and_guest_guard(hass):
    from dataclasses import replace

    provider = setup_target(hass)
    target = capabilities(hass, provider)["start"]
    dispatch = AsyncMock()
    executor = CommandExecutor(hass, transport=dispatch, budget=1)
    for unsafe in [
        replace(context(), guest=True),
        replace(context(), fresh=False),
        replace(context(), current_session="next"),
        replace(context(), commissioned_charger=False),
    ]:
        assert (await executor.execute("a", target, unsafe)).status == "unsafe"
    assert not dispatch.called
    hass.states.async_set("switch.charge", "on")
    assert (await executor.execute("same", target, context())).status == "already_observed"
    assert not dispatch.called
    hass.states.async_set("switch.charge", "off")
    assert (await executor.execute("a", target, context())).status == "awaiting_observation"
    stop = capabilities(hass, provider)["stop"]
    assert (await executor.execute("a", stop, context())).status == "idempotency_conflict"
    hass.states.async_set("switch.charge", "on")
    assert (await executor.execute("a", target, context())).status == "observed"
    assert (await executor.execute("b", stop, context())).status == "budget_exhausted"


async def test_number_constraints_and_registry_rename(hass):
    provider = setup_target(hass)
    target = capabilities(hass, provider)["limit"]
    dispatch = AsyncMock()
    executor = CommandExecutor(hass, transport=dispatch)
    for value in [None, float("nan"), 0, 101, 70.5]:
        assert (await executor.execute("bad", target, context(), value)).status == "invalid_value"
    assert not dispatch.called
    er.async_get(hass).async_update_entity("number.limit", new_entity_id="number.renamed")
    hass.states.async_remove("number.limit")
    hass.states.async_set("number.renamed", "70", {"min": 50, "max": 100, "step": 1})
    assert (await executor.execute("limit", target, context(), 80)).status == "awaiting_observation"
    assert dispatch.call_args.args[2] == {"entity_id": "number.renamed", "value": 80}


async def test_actual_mocked_ha_dispatch_matches_preserved_node_red_routes(hass):
    import json
    from pathlib import Path

    provider = setup_target(hass)
    calls = []

    async def record(call):
        calls.append((call.domain, call.service, dict(call.data)))

    hass.services.async_register("switch", "turn_on", record)
    executor = CommandExecutor(hass, transport=hass.services.async_call)
    result = await executor.execute("ha", capabilities(hass, provider)["start"], context())
    assert result.status == "awaiting_observation"
    assert calls == [("switch", "turn_on", {"entity_id": "switch.charge"})]
    routes = set()
    for path in (Path(__file__).parents[1] / "node-red").glob("*.json"):
        for node in json.loads(path.read_text()):
            if node.get("type") == "api-call-service":
                routes.add((node.get("domain"), node.get("service")))
    assert {("switch", "turn_on"), ("switch", "turn_off"), ("number", "set_value")} <= routes


async def test_pre_dispatch_write_fallback_and_capability_ambiguity(hass):
    from custom_components.ev_charge_manager.executor import select_capability

    provider = setup_target(hass)
    missing = register_provider(hass, {"soc": "sensor.no_control"}, "read_only")
    vehicle = {
        "providers": [missing, provider],
        "provider_policy": {"write_provider": "read_only", "write_fallback": False},
    }
    assert select_capability(hass, vehicle, "start") is None
    vehicle["provider_policy"]["write_fallback"] = True
    assert select_capability(hass, vehicle, "start").provider == provider["id"]
    er.async_get(hass).async_get_or_create(
        "switch", "demo", "second_charge", device_id=provider["device"], translation_key="charging"
    )
    assert "start" not in capabilities(hass, provider)


async def test_rebound_entity_and_conflicting_owner_are_rejected(hass, freezer):
    from dataclasses import replace
    from datetime import timedelta

    provider = setup_target(hass)
    target = capabilities(hass, provider)["start"]
    dispatch = AsyncMock()
    executor = CommandExecutor(hass, transport=dispatch)
    assert (await executor.execute("one", target, context())).status == "awaiting_observation"
    assert (
        await executor.execute("two", target, replace(context(), owner="brain"))
    ).status == "ownership_conflict"
    er.async_get(hass).async_update_entity("switch.charge", device_id=None)
    assert (await executor.execute("one", target, context())).status == "unsupported"
    assert dispatch.await_count == 1
    er.async_get(hass).async_update_entity("switch.charge", device_id=provider["device"])
    freezer.tick(timedelta(minutes=3))
    assert (await executor.execute("three", target, context())).status == "stale"


async def test_native_reviewed_command_mapping_stays_inert_and_device_owned(hass):
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from .test_manager import model

    config = model(hass)
    provider = config["vehicles"][0]["providers"][0]
    row = er.async_get(hass).async_get_or_create(
        "switch", "demo", "manual_control", device_id=provider["device"]
    )
    hass.services.async_register("switch", "turn_on", AsyncMock())
    entry = MockConfigEntry(domain="ev_charge_manager", data=config)
    entry.add_to_hass(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    fid = result["flow_id"]
    await hass.config_entries.options.async_configure(fid, {"next_step_id": "command_mapping"})
    await hass.config_entries.options.async_configure(fid, {"provider": "car:custom"})
    wrong = register_provider(hass, {"charging": "switch.wrong_device"}, "other")
    result = await hass.config_entries.options.async_configure(
        fid, {"start_stop": wrong["fields"]["charging"]}
    )
    assert result["errors"]["base"] == "invalid_mapping"
    result = await hass.config_entries.options.async_configure(fid, {"start_stop": row.entity_id})
    assert result["type"] == "menu"
    await hass.config_entries.options.async_configure(fid, {"next_step_id": "finish"})
    saved = entry.options["vehicles"][0]["providers"][0]
    assert saved["command_entities"]["start_stop"] == row.id
    assert capabilities(hass, saved)["start"].registry_id == row.id
    assert CommandExecutor(hass).transport is None
