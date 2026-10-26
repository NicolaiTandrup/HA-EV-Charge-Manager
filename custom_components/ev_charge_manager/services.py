"""Own-state simulation services only. No vehicle or charger service dispatch."""

import voluptuous as vol
from homeassistant.core import SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util

from .association import associate
from .brain import CONNECTED, normalize
from .command import Intent
from .const import DOMAIN
from .policies import charger_enabled
from .simulation import simulate_probe


def async_register(hass, coordinator):
    async def authorize(call):
        # Reconcile pending source events before deciding that a session is unknown.
        await coordinator.async_refresh()
        charger = next(
            (c for c in coordinator.config.get("chargers", []) if c["id"] == call.data["charger"]),
            None,
        )
        source = coordinator.chargers.source(charger) if charger else None
        state = hass.states.get(source) if source else None
        now = dt_util.utcnow()
        if (
            not charger
            or not charger_enabled(coordinator.config, charger)
            or charger.get("guest_policy", "manual") != "manual"
            or not state
            or not 0 <= (now - state.last_reported).total_seconds() <= coordinator.registry.ttl
            or normalize(state.state) not in CONNECTED
        ):
            raise ServiceValidationError("Fresh physical connection required")
        try:
            coordinator.sessions.authorize_guest(call.data["charger"], call.data["session_id"])
        except ValueError as err:
            raise ServiceValidationError(str(err)) from err
        await coordinator.async_save()
        await coordinator.async_request_refresh()
        return {"mode": "simulation", "authorized": True, "physical_commands": 0}

    async def command(call):
        session = coordinator.sessions.items.get(call.data["charger"])
        observed = coordinator.data["sessions"].get(call.data["charger"], {})
        row = coordinator.data["assignments"].get(call.data["charger"], {})
        now = dt_util.utcnow()
        age = (now - coordinator.data["updated_at"]).total_seconds()
        mapping = next(
            (c for c in coordinator.config.get("chargers", []) if c["id"] == call.data["charger"]),
            None,
        )
        source = coordinator.chargers.source(mapping) if mapping else None
        state = hass.states.get(source) if source else None
        source_fresh = bool(
            state
            and mapping
            and charger_enabled(coordinator.config, mapping)
            and (
                bool(session and session.vehicle)
                or mapping.get("guest_policy", "manual") == "manual"
            )
            and normalize(state.state) in CONNECTED
            and 0 <= (now - state.last_reported).total_seconds() <= coordinator.registry.ttl
        )
        snapshots = coordinator.registry.snapshot(now)
        health = coordinator.registry.assess(snapshots)
        vehicle_health = health.get(session.vehicle, {}) if session else {}
        snapshot_safe = not (session and session.vehicle) or (
            "charging_while_disconnected" not in vehicle_health.get("issues", [])
            and (call.data["owner"] != "optimizer" or vehicle_health.get("forecast_safe", False))
        )
        intent = Intent(
            call.data["key"],
            call.data["session_id"],
            call.data["owner"],
            call.data["action"],
            call.data.get("value"),
        )
        optimizer_safe = True
        if intent.owner == "optimizer" and session and session.vehicle:
            optimizer_safe = any(
                forecast.valid
                and (
                    intent.action != "start"
                    or any(a.start <= now < a.end for a in forecast.allocations)
                )
                and forecast.updated_at
                and 0 <= (now - forecast.updated_at).total_seconds() <= 2400
                and coordinator.sites[site_id].site["zone_state"] == mapping["zone_state"]
                and (
                    coordinator.sites[site_id].site.get("price_source") != "energy_price_engine"
                    or bool(coordinator.price_consumer.slots(coordinator.sites[site_id].site, now))
                )
                for site_id, forecasts in coordinator.data["forecasts"].items()
                for key, forecast in forecasts.items()
                if key == session.vehicle
            )
        result = coordinator.commands.propose(
            intent,
            current_session=session.id if session else None,
            fresh=source_fresh
            and optimizer_safe
            and snapshot_safe
            and 0 <= age <= 30
            and observed.get("session_id") == call.data["session_id"],
            authorized=bool(
                session and (session.authorized or (session.vehicle and row.get("valid")))
            ),
            guest=not bool(session and session.vehicle),
        )
        return {"mode": "simulation", "result": result, "physical_commands": 0}

    async def association(call):
        return await associate(
            coordinator, call.data["charger"], call.data["session_id"], call.data["vehicle"]
        )

    async def probe(call):
        return {"mode": "simulation", **simulate_probe(**call.data)}

    hass.services.async_register(
        DOMAIN,
        "simulate_vehicle_association",
        association,
        schema=vol.Schema(
            {
                vol.Required("charger"): str,
                vol.Required("session_id"): str,
                vol.Required("vehicle"): str,
            }
        ),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        "simulate_guest_authorization",
        authorize,
        schema=vol.Schema({vol.Required("charger"): str, vol.Required("session_id"): str}),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        "simulate_command",
        command,
        schema=vol.Schema(
            {
                vol.Required("charger"): str,
                vol.Required("session_id"): str,
                vol.Required("key"): str,
                vol.Required("owner"): str,
                vol.Required("action"): str,
                vol.Optional("value"): vol.Coerce(float),
            }
        ),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        "simulate_probe",
        probe,
        schema=vol.Schema(
            {
                vol.Required("charger"): str,
                vol.Required("candidates"): [str],
                vol.Required("samples"): [dict],
                vol.Required("commissioned_vehicles"): [str],
                vol.Required("commissioned_chargers"): [str],
                vol.Optional("guest", default=False): bool,
            }
        ),
        supports_response=SupportsResponse.ONLY,
    )


def async_unregister(hass):
    for name in (
        "simulate_guest_authorization",
        "simulate_probe",
        "simulate_command",
        "simulate_vehicle_association",
    ):
        hass.services.async_remove(DOMAIN, name)
