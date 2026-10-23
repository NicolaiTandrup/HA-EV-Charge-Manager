from datetime import UTC, datetime, timedelta

import pytest

from custom_components.ev_charge_manager.brain import Brain, Reading

NOW = datetime(2026, 10, 23, tzinfo=UTC)


def states(**changes):
    values = {
        "sensor.one": "charging",
        "sensor.two": "charging",
        "binary_sensor.a": "on",
        "binary_sensor.b": "on",
        "device_tracker.a": "home",
        "device_tracker.b": "work",
        "input_boolean.manual": "off",
    }
    values.update(changes)
    return {k: Reading(v, NOW) for k, v in values.items()}


def test_two_vehicles_two_sites(config):
    rows = Brain(config).evaluate(states(), NOW)
    assert [r["car"] for r in rows.values()] == ["a", "b"]


def test_disconnect_replug_requires_evidence(config):
    brain = Brain(config)
    brain.evaluate(states(), NOW)
    r = brain.evaluate(states(**{"sensor.one": "car_disconnected"}), NOW)["one"]
    assert not r["valid"] and r["car"] is None and r["last_associated_vehicle"] == "a"
    r = brain.evaluate(states(**{"device_tracker.a": "unknown"}), NOW)["one"]
    assert not r["valid"]  # historical identity is never a current association
    assert brain.evaluate(states(), NOW)["one"]["car"] == "a"


def test_ambiguous_vehicles(config):
    r = Brain(config).evaluate(states(**{"device_tracker.b": "home"}), NOW)
    assert r["one"]["mode"] == "ambiguous" and r["one"]["car"] is None


def test_one_vehicle_two_chargers_no_iteration_bias(config):
    config["chargers"][1]["zone_state"] = "home"
    r = Brain(config).evaluate(states(), NOW)
    assert all(x["mode"] == "ambiguous" for x in r.values())


def test_unknown_gps_and_cable_off_keep_established_session(config):
    brain = Brain(config)
    brain.evaluate(states(), NOW)
    r = brain.evaluate(states(**{"device_tracker.a": "unknown", "binary_sensor.a": "off"}), NOW)
    assert r["one"]["car"] == "a"


def test_manual_latches_until_disconnect(config):
    brain = Brain(config)
    brain.evaluate(states(), NOW)
    assert (
        brain.evaluate(states(**{"input_boolean.manual": "on"}), NOW)["one"]["mode"]
        == "manual_until_disconnect"
    )
    assert brain.evaluate(states(), NOW)["one"]["mode"] == "manual_until_disconnect"
    brain.evaluate(states(**{"sensor.one": "disconnected", "input_boolean.manual": "on"}), NOW)
    assert (
        brain.evaluate(states(**{"input_boolean.manual": "on"}), NOW)["one"]["mode"]
        == "auto_assigned"
    )


def test_manual_without_identity_does_not_guess(config):
    r = Brain(config).evaluate(states(**{"input_boolean.manual": "on"}), NOW)["one"]
    assert r["mode"] == "manual_until_disconnect" and not r["valid"]


@pytest.mark.parametrize("source", ["sensor.one", "binary_sensor.a"])
def test_missing_source_suppresses_assignment(config, source):
    brain = Brain(config)
    brain.evaluate(states(), NOW)
    data = states()
    del data[source]
    r = brain.evaluate(data, NOW)["one"]
    assert not r["valid"] and r["car"] is None
    assert brain.evaluate(states(), NOW)["one"]["car"] == "a"


def test_stale_all_sources_connection_loss(config):
    brain = Brain(config)
    brain.evaluate(states(), NOW)
    assert not any(
        x["valid"] for x in brain.evaluate(states(), NOW + timedelta(seconds=901)).values()
    )


def test_restart_reconstructs_only_with_fresh_evidence(config):
    assert Brain(config).evaluate(states(), NOW)["one"]["car"] == "a"
    assert not Brain(config).evaluate(states(**{"device_tracker.a": "unknown"}), NOW)["one"][
        "valid"
    ]


def test_primary_off_beats_fallback_on_and_unknown_uses_fallback(config):
    config["vehicles"][0]["cable_fallback"] = "binary_sensor.fallback"
    assert not Brain(config).evaluate(
        states(**{"binary_sensor.a": "off", "binary_sensor.fallback": "on"}), NOW
    )["one"]["valid"]
    assert Brain(config).evaluate(
        states(**{"binary_sensor.a": "unknown", "binary_sensor.fallback": "on"}), NOW
    )["one"]["valid"]


@pytest.mark.parametrize(
    "status", ["ready_to_charge", "awaiting-start", "charging", "complete", "completed"]
)
def test_status_normalization(config, status):
    assert Brain(config).evaluate(states(**{"sensor.one": status}), NOW)["one"]["valid"]
