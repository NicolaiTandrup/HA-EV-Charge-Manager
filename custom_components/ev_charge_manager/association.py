"""Explicit reviewed identity for a simulated, verified current plug session."""

from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

from .brain import CONNECTED, normalize
from .policies import eligible


async def associate(coordinator, charger_id, session_id, vehicle_id):
    await coordinator.async_refresh()
    charger = next((c for c in coordinator.config["chargers"] if c["id"] == charger_id), None)
    vehicle = next((v for v in coordinator.registry.vehicles if v["id"] == vehicle_id), None)
    session = coordinator.sessions.items.get(charger_id)
    if (
        not coordinator.config.get("brain_enabled", True)
        or not charger
        or not vehicle
        or not eligible(coordinator.config, vehicle, charger)
        or session is None
        or session.id != session_id
        or session.authorized
        or session.needs_reconciliation
        or session.vehicle not in {None, vehicle_id}
    ):
        raise ServiceValidationError("Current eligible non-guest plug session required")
    source = coordinator.chargers.source(charger)
    status = coordinator.hass.states.get(source) if source else None
    now = dt_util.utcnow()
    fields = coordinator.registry.snapshot(now).get(vehicle_id, {})
    cable, tracker = fields.get("cable"), fields.get("tracker")
    if (
        not status
        or normalize(status.state) not in CONNECTED
        or not 0 <= (now - status.last_reported).total_seconds() <= coordinator.registry.ttl
        or not cable
        or cable.value != "on"
        or not tracker
        or tracker.value != charger["zone_state"]
    ):
        raise ServiceValidationError(
            "Fresh connected charger, cable and same-site vehicle required"
        )
    if any(
        key != charger_id and item.car == vehicle_id
        for key, item in coordinator.brain.sessions.items()
    ):
        raise ServiceValidationError("Vehicle is reserved by another physical session")
    brain = coordinator.brain.sessions[charger_id]
    brain.car = vehicle_id
    brain.reviewed = True
    session.vehicle = vehicle_id
    await coordinator.async_save()
    await coordinator.async_refresh()
    current = coordinator.sessions.items.get(charger_id)
    row = coordinator.data["assignments"].get(charger_id, {})
    if (
        current is None
        or current.id != session_id
        or not row.get("valid")
        or row.get("car") != vehicle_id
    ):
        raise ServiceValidationError("Physical session changed during review")
    return {"mode": "simulation", "associated": True, "physical_commands": 0}
