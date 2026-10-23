"""Provider reconciliation preserves priority while suppressing unsafe forecasts."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.ev_charge_manager.vehicle import FieldValue, snapshot_health

from .test_manager import model

NOW = datetime(2026, 10, 23, 12, tzinfo=UTC)


def fields():
    return {
        key: FieldValue(value, f"sensor.{key}", "custom", NOW, {})
        for key, value in {
            "soc": "60",
            "target": "70",
            "cable": "on",
            "tracker": "home",
            "charging": "off",
        }.items()
    }


@pytest.mark.parametrize("skew,safe", [(120, True), (120.001, False)])
def test_skew_boundary_and_required_field_scope(skew, safe):
    data = fields()
    data["soc"] = replace(data["soc"], reported_at=NOW + timedelta(seconds=skew))
    # Neither old idle power nor optional odometer should block a coherent plan.
    data["power"] = FieldValue("11", "sensor.power", "fleet", NOW - timedelta(days=1), {})
    data["odometer"] = FieldValue("500", "sensor.odometer", "fleet", NOW - timedelta(days=1), {})
    health = snapshot_health(data, 120)
    assert health["forecast_safe"] is safe
    assert health["report_skew_seconds"] == skew
    assert health["issues"] == ([] if safe else ["report_time_skew"])


def test_active_power_required_and_included_in_skew():
    data = fields()
    data["charging"] = replace(data["charging"], value="on")
    assert snapshot_health(data)["missing_fields"] == ["power"]
    data["power"] = FieldValue("7", "sensor.power", "fleet", NOW - timedelta(seconds=121), {})
    assert snapshot_health(data)["issues"] == ["report_time_skew"]


def test_connection_contradiction_is_not_reconciled_by_switching_provider():
    data = fields()
    data["cable"] = replace(data["cable"], value="off")
    data["charging"] = replace(data["charging"], value="on")
    data["power"] = FieldValue("7", "sensor.power", "fleet", NOW, {})
    assert snapshot_health(data)["issues"] == ["charging_while_disconnected"]


@pytest.mark.parametrize("brain", [True, False])
async def test_report_skew_blocks_forecast_then_recovers_without_io(hass, freezer, brain):
    config = model(hass, brain=brain)
    config.pop("snapshot_skew_seconds")
    now = dt_util.utcnow()
    # Fresh valid Custom remains preferred over a newer fallback value.
    hass.states.async_set("sensor.fleet_soc", "90")
    config["vehicles"][0]["providers"].append(
        {"id": "fleet", "fields": {"soc": "sensor.fleet_soc"}}
    )
    freezer.move_to(now + timedelta(seconds=121))
    hass.states.async_set("sensor.car_soc", "61")
    entry = MockConfigEntry(domain="ev_charge_manager", data=config)
    entry.add_to_hass(hass)
    with patch("homeassistant.core.ServiceRegistry.async_call", new_callable=AsyncMock) as calls:
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        c = entry.runtime_data
        health = c.data["vehicle_health"]["car"]
        assert health["issues"] == ["report_time_skew"]
        f = c.data["forecasts"]["home"]["car"]
        assert not f.valid and "report_time_skew" in f.reason
        assert f.expected_finish is None and f.expected_soc_at_0700 is None
        assert c.data["vehicles"]["car"]["soc"].provider == "custom"
        assert c.data["vehicles"]["car"]["soc"].value == "61"
        for field, value in {
            "target": "65",
            "cable": "on",
            "tracker": "home",
            "charging": "off",
        }.items():
            hass.states.async_set(f"sensor.car_{field}", value)
        await c.async_refresh()
        assert c.data["vehicle_health"]["car"]["forecast_safe"]
        assert c.data["forecasts"]["home"]["car"].valid
        calls.assert_not_called()
        assert await hass.config_entries.async_unload(entry.entry_id)


async def test_configured_skew_tolerance_applies_to_forecasts(hass, freezer):
    config = model(hass)
    config["snapshot_skew_seconds"] = 180
    now = dt_util.utcnow()
    freezer.move_to(now + timedelta(seconds=121))
    hass.states.async_set("sensor.car_soc", "61")
    entry = MockConfigEntry(domain="ev_charge_manager", data=config)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.runtime_data.data["forecasts"]["home"]["car"].valid
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_contradiction_preserves_session_but_blocks_forecast_and_intent(hass):
    entry = MockConfigEntry(domain="ev_charge_manager", data=model(hass))
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    c = entry.runtime_data
    sid = c.sessions.items["charger"].id
    hass.states.async_set("sensor.car_cable", "off")
    hass.states.async_set("sensor.car_charging", "on")
    hass.states.async_set("sensor.car_power", "7", {"unit_of_measurement": "kW"})
    # Service guard reads current inputs before a coordinator update can run.
    result = await hass.services.async_call(
        "ev_charge_manager",
        "simulate_command",
        {
            "charger": "charger",
            "session_id": sid,
            "key": "unsafe",
            "owner": "optimizer",
            "action": "start",
        },
        blocking=True,
        return_response=True,
    )
    assert result["result"] == "unsafe_session"
    assert c.commands.estimated_requests == 0
    await c.async_refresh()
    assert c.sessions.items["charger"].id == sid
    assert c.data["assignments"]["charger"]["valid"]
    f = c.data["forecasts"]["home"]["car"]
    assert not f.valid and "charging_while_disconnected" in f.reason
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_brain_only_simulation_does_not_require_optimizer_fields(hass):
    config = model(hass, optimizer=False)
    mapping = config["vehicles"][0]["providers"][0]["fields"]
    for field in ("soc", "target", "power"):
        mapping.pop(field)
    entry = MockConfigEntry(domain="ev_charge_manager", data=config)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    c = entry.runtime_data
    sid = c.sessions.items["charger"].id
    assert c.data["assignments"]["charger"]["valid"]
    result = await hass.services.async_call(
        "ev_charge_manager",
        "simulate_command",
        {
            "charger": "charger",
            "session_id": sid,
            "key": "brain",
            "owner": "brain",
            "action": "start",
        },
        blocking=True,
        return_response=True,
    )
    assert result["result"] == "simulated" and result["physical_commands"] == 0
    assert await hass.config_entries.async_unload(entry.entry_id)
