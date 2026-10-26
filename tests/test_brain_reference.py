"""Execute the byte-identical old Brain in a log-only JavaScript sandbox."""

import json
import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from custom_components.ev_charge_manager.brain import Brain, Reading


@pytest.mark.parametrize("cables", [("on", "off"), ("off", "off"), ("on", "on")])
def test_original_brain_known_unknown_and_approved_ambiguity_change(cables):
    if not shutil.which("node"):
        pytest.skip("Node.js required for original Brain parity")
    flow = json.loads(
        (Path(__file__).parents[1] / "node-red/EV-Charger-Brain-v1.0.json").read_text()
    )
    function = next(n["func"] for n in flow if n.get("name") == "EV Charger Brain v1.0")
    now = datetime(2026, 10, 25, 12, tzinfo=UTC)
    values = {
        "sensor.garage_status": "charging",
        "sensor.hegn_status": "disconnected",
        "switch.garage_is_enabled": "off",
        "switch.hegn_is_enabled": "off",
        "binary_sensor.ellingo_charger": cables[0],
        "binary_sensor.charger": cables[1],
        "device_tracker.ellingo_location_tracker_2": "home",
        "device_tracker.location_tracker": "home",
    }
    script = """const fs=require('fs');const x=JSON.parse(fs.readFileSync(0,'utf8'));
const NativeDate=Date;global.Date=class extends NativeDate{constructor(...a){super(...(a.length?a:[x.now]));}static now(){return new NativeDate(x.now).getTime();}};
const states=Object.fromEntries(Object.entries(x.values).map(([k,v])=>[k,{state:v,updatedTs:Date.now()}]));
const cache={ev_brain_v10_states:states};const flow={get:k=>cache[k],set:(k,v)=>cache[k]=v};
const fn=new Function('msg','flow','node',x.fn);const out=fn({_ev_watchdog:true},flow,{status:()=>{}});
console.log(JSON.stringify({session:cache.ev_brain_v10_sessions.garage,services:out[0]}));"""
    result = subprocess.run(
        ["node", "-e", script],
        input=json.dumps({"fn": function, "now": now.isoformat(), "values": values}),
        text=True,
        capture_output=True,
        check=True,
        env={**os.environ, "TZ": "Europe/Copenhagen"},
    )
    legacy = json.loads(result.stdout)
    config = {
        "vehicles": [
            {
                "id": "ellingo",
                "name": "A",
                "cable": "binary_sensor.ellingo_charger",
                "tracker": "device_tracker.ellingo_location_tracker_2",
            },
            {
                "id": "blue_flux",
                "name": "B",
                "cable": "binary_sensor.charger",
                "tracker": "device_tracker.location_tracker",
            },
        ],
        "chargers": [{"id": "garage", "status": "sensor.garage_status", "zone_state": "home"}],
    }
    native = Brain(config).evaluate(
        {key: Reading(value, now) for key, value in values.items()}, now
    )["garage"]
    assert legacy["services"] == []  # Sandbox never reaches HA; original runs log-only.
    if cables == ("on", "off"):
        assert native["car"] == legacy["session"]["assignedCar"] == "ellingo"
        assert native["valid"]
    elif cables == ("off", "off"):
        assert native["car"] is legacy["session"]["assignedCar"] is None
        assert not native["valid"]
    else:
        # Issue #3 explicitly supersedes old defaultCar guessing. Preserve this
        # intentional safety difference, rather than silently porting the guess.
        assert legacy["session"]["assignedCar"] == "ellingo"
        assert native["mode"] == "ambiguous" and native["car"] is None
