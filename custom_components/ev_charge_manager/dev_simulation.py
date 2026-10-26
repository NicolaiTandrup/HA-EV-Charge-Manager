"""Pure opt-in scenario previews, strictly separated from live HA input/authority."""

import json
from copy import deepcopy
from dataclasses import asdict
from datetime import timedelta
from pathlib import Path

from .brain import Brain, Reading
from .planner import PriceSlot, Vehicle, plan_site, utc
from .sessions import Sessions

# Package data is loaded once with the integration module, not from async form
# callbacks or source refreshes. It is never a user-owned configuration file.
_CATALOG = json.loads(Path(__file__).with_name("dev_scenarios.json").read_text())
if _CATALOG.get("synthetic") is not True or _CATALOG.get("schema_version") != 1:
    raise ValueError("Synthetic fixture catalog required")


def catalog():
    return deepcopy(_CATALOG)


def scenarios():
    return {key: row["name"] for key, row in catalog()["scenarios"].items()}


def simulate(scenario, now):
    data = catalog()
    spec = data["scenarios"][scenario]
    now = utc(now)
    sites = [
        {
            "id": f"demo_site_{i}",
            "zone_state": f"demo_zone_{i}",
            "timezone": "Europe/Copenhagen",
            "grid_kw": spec["grid_kw"],
        }
        for i in range(spec["sites"])
    ]
    vehicles = [
        {
            "id": f"demo_car_{i}",
            "name": f"Demo vehicle {i + 1}",
            "cable": f"fixture.car_{i}.cable",
            "tracker": f"fixture.car_{i}.tracker",
            "soc": 40 + i * 3,
            "target": 65,
            "capacity_kwh": 75,
            "max_kw": 11,
            "profile_example": {
                "read": "tesla_custom",
                "write": "tesla_custom" if i % 2 == 0 else "tesla_fleet",
            },
        }
        for i in range(spec["vehicles"])
    ]
    chargers = [
        {
            "id": f"demo_charger_{i}",
            "name": f"Demo Easee {i + 1}",
            "status": f"fixture.charger_{i}.status",
            "zone_state": sites[i % len(sites)]["zone_state"],
        }
        for i in range(len(vehicles))
    ]
    config = {"vehicles": vehicles, "chargers": chargers}
    brain, sessions, values = Brain(config), Sessions(), {}
    for i, vehicle in enumerate(vehicles):
        values[vehicle["cable"]] = "off"
        values[vehicle["tracker"]] = sites[i % len(sites)]["zone_state"]
        values[chargers[i]["status"]] = "disconnected"
    trace, published = [], {}

    def observe(at):
        rows = brain.evaluate({key: Reading(value, at) for key, value in values.items()}, at)
        for charger in chargers:
            row = rows[charger["id"]]
            current = sessions.update(
                charger["id"],
                values[charger["status"]],
                row.get("car") if row["valid"] else None,
                now=at,
                reported_at=at,
                source_device=charger["id"],
            )
            published[charger["id"]] = {
                "session_id": "fixture_session_" + charger["id"] if current else None,
                "vehicle": current.vehicle if current else None,
                "simulated_guest_authorized": bool(current and current.authorized),
            }
        return rows

    observe(now)
    mode = spec["mode"]
    at = now
    if mode == "guest":
        values[chargers[0]["status"]] = "charging"
        observe(at)
        current = sessions.items[chargers[0]["id"]]
        sessions.authorize_guest(chargers[0]["id"], current.id)
        at += timedelta(days=spec["guest_days"])
    elif mode == "simultaneous":
        for vehicle, charger in zip(vehicles, chargers, strict=True):
            values[vehicle["cable"]], values[charger["status"]] = "on", "charging"
    else:
        for i, (vehicle, charger) in enumerate(zip(vehicles, chargers, strict=True)):
            at = now + timedelta(seconds=15 * i)
            values[vehicle["cable"]], values[charger["status"]] = "on", "charging"
            observe(at)
            trace.append(
                {"at": at.isoformat(), "event": "synthetic_plug", "charger": charger["id"]}
            )
        if mode == "offline":
            values[chargers[0]["status"]] = "unavailable"
        elif mode == "movement":
            values[vehicles[0]["tracker"]] = sites[1]["zone_state"]
        elif mode == "restart":
            sessions = Sessions(sessions.persistent())
            brain = Brain(config)  # No inferred uninterrupted physical continuity.
    rows = observe(at)
    start = at.replace(minute=at.minute // 15 * 15, second=0, microsecond=0)
    prices = data["fixture_final_prices_dkk_per_kwh"]
    slots = [
        PriceSlot(
            start + timedelta(minutes=15 * i),
            start + timedelta(minutes=15 * (i + 1)),
            prices[i % len(prices)],
        )
        for i in range(192)
    ]
    forecasts, headroom = {}, {}
    for site in sites:
        managed = []
        for vehicle in vehicles:
            matches = [
                charger
                for charger in chargers
                if charger["zone_state"] == site["zone_state"]
                and rows[charger["id"]].get("valid")
                and rows[charger["id"]].get("car") == vehicle["id"]
                and not published[charger["id"]]["simulated_guest_authorized"]
            ]
            if matches:
                managed.append(
                    Vehicle(
                        vehicle["id"],
                        vehicle["soc"],
                        vehicle["target"],
                        vehicle["capacity_kwh"],
                        vehicle["max_kw"],
                        connected=values[vehicle["tracker"]] == site["zone_state"],
                    )
                )
        uncertain = any(
            charger["zone_state"] == site["zone_state"]
            and values[charger["status"]] in {"charging", "unavailable"}
            and not rows[charger["id"]]["valid"]
            for charger in chargers
        )
        power = (
            max(0, site["grid_kw"] - spec["guest_power_kw"])
            if uncertain and spec.get("guest_power_kw") is not None
            else 0
            if uncertain
            else site["grid_kw"]
        )
        headroom[site["id"]] = power
        planned = plan_site(managed, slots, at, timezone=site["timezone"], grid_kw=power)
        forecasts[site["id"]] = {key: asdict(value) for key, value in planned.items()}
    report = {
        "schema_version": 1,
        "scenario": scenario,
        "simulation_only": True,
        "physical_commands": 0,
        "source": "portable_synthetic_fixture",
        "generated_at": now,
        "fixture_evaluated_at": at,
        "price_basis": "synthetic_final_inclusive_not_tariff_defaults",
        "sites": sites,
        "vehicles": vehicles,
        "chargers": chargers,
        "assignments": rows,
        "sessions": published,
        "forecasts": forecasts,
        "available_site_kw": headroom,
        "trace": trace,
        "explanations": {
            key: {
                "ambiguous": "Multiple eligible connections remain; no default-car identity guess.",
                "unavailable": "Charger status is unavailable; no managed charge proposal.",
                "pending_match": "No reliable known-car match; guest authority is manual and simulated.",
                "auto_assigned": "Reliable fixture association; planner stages and supply limits apply.",
            }.get(row["mode"], row["mode"])
            for key, row in rows.items()
        },
        "notes": [
            "Synthetic reports never enter the real registry, history, budgets or command journal.",
            "A continued HA session token does not prove physical continuity after restart.",
        ],
    }
    return json.loads(json.dumps(report, default=lambda value: value.isoformat()))


def publish_preview(coordinator, scenario):
    from homeassistant.util import dt as dt_util

    coordinator.simulation_preview = simulate(scenario, dt_util.utcnow())
    coordinator.async_set_updated_data(
        {**coordinator.data, "simulation_preview": coordinator.simulation_preview}
    )
    return coordinator.simulation_preview
