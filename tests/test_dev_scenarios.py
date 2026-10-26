"""Portable fixture preview must never become live input, authority or history."""

from datetime import UTC, datetime

import pytest

from custom_components.ev_charge_manager.dev_simulation import scenarios, simulate

NOW = datetime(2026, 10, 26, 12, tzinfo=UTC)


@pytest.mark.parametrize(
    "case",
    [
        "two_tesla_two_easee",
        "six_vehicle_shared_sites",
        "unknown_guest",
        "charger_offline",
        "vehicle_changes_site",
        "unexpected_restart",
        "simultaneous_ambiguity",
    ],
)
def test_portable_scenarios_are_explicitly_synthetic_and_safe(case):
    report = simulate(case, NOW)
    assert report["simulation_only"] is True and report["physical_commands"] == 0
    assert report["scenario"] == case and report["source"] == "portable_synthetic_fixture"
    assert report == simulate(case, NOW)
    assert report["explanations"]
    if case in {"two_tesla_two_easee", "six_vehicle_shared_sites"}:
        assert all(row["valid"] for row in report["assignments"].values())
        assert any(f["valid"] for rows in report["forecasts"].values() for f in rows.values())
    if case == "unknown_guest":
        assert any(s["simulated_guest_authorized"] for s in report["sessions"].values())
    if case == "simultaneous_ambiguity":
        assert all(row["mode"] == "ambiguous" for row in report["assignments"].values())


async def test_native_options_preview_does_not_modify_real_configuration(hass):
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.ev_charge_manager.config_flow import defaults

    entry = MockConfigEntry(domain="ev_charge_manager", data=defaults())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    flow = await hass.config_entries.options.async_init(entry.entry_id)
    fid = flow["flow_id"]
    await hass.config_entries.options.async_configure(fid, {"next_step_id": "simulation_scenario"})
    result = await hass.config_entries.options.async_configure(
        fid, {"scenario": "two_tesla_two_easee"}
    )
    assert result["type"] == "menu"
    c = entry.runtime_data
    assert c.data["simulation_preview"]["simulation_only"] is True
    assert c.config["vehicles"] == c.config["chargers"] == c.config["sites"] == []
    assert c.data["forecasts"] == {} and c.data["assignments"] == {}
    assert c.executor.requests == c.commands.estimated_requests == 0
    assert c.executor.transport is None
    assert set(scenarios()) >= {"unknown_guest", "unexpected_restart"}
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert not hass.services.has_service("ev_charge_manager", "simulate_dev_scenario")
