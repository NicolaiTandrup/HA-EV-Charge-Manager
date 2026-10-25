"""Dormant command boundary; no transport or live-service wiring by default.

Only an explicitly injected transport can dispatch. Integration startup and public
services never construct this executor with a transport. Tests inject mock services.
Routes reuse the preserved Node-RED switch/number semantics, without vendor RPCs.
"""

from asyncio import Lock, timeout
from dataclasses import dataclass, replace
from math import isfinite

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from .providers import adapter
from .vehicle import provider_order


@dataclass(frozen=True)
class Capability:
    provider: str
    device: str
    registry_id: str
    action: str
    domain: str
    service: str
    desired: str | None = None


@dataclass(frozen=True)
class CommandContext:
    session_id: str
    current_session: str
    owner: str
    fresh: bool
    authorized: bool
    commissioned_vehicle: bool = False
    commissioned_charger: bool = False
    guest: bool = False


@dataclass(frozen=True)
class Result:
    status: str
    reason: str = ""
    # Observation is of the mapped entity, not proof of delivered energy/SoC.
    observation_scope: str = "entity_state_only"


def capabilities(hass, provider):
    """Unambiguous semantic suggestions; no display-name or entity-suffix matching."""
    found = {}
    for entity in er.async_entries_for_device(er.async_get(hass), provider["device"]):
        if entity.disabled_by or entity.platform == "ev_charge_manager":
            continue
        domain = entity.domain
        key = adapter(entity).semantic(entity)
        routes = []
        if domain == "switch" and key in {"charging", "charger"}:
            routes = [("start", "turn_on", "on"), ("stop", "turn_off", "off")]
        elif domain == "switch" and key in {"enabled", "charger_enabled"}:
            routes = [("enable", "turn_on", "on"), ("disable", "turn_off", "off")]
        elif domain == "number" and key in {"charge_limit", "charge_limit_soc"}:
            routes = [("limit", "set_value", None)]
        elif domain == "number" and key in {"charge_current", "charging_amps"}:
            routes = [("current", "set_value", None)]
        for action, service, desired in routes:
            if hass.services.has_service(domain, service):
                found.setdefault(action, []).append(
                    Capability(
                        provider["id"],
                        provider["device"],
                        entity.id,
                        action,
                        domain,
                        service,
                        desired,
                    )
                )
    result = {action: rows[0] for action, rows in found.items() if len(rows) == 1}
    # Reviewed manual registry references override suggestions, without name guesses.
    routes = {
        "start_stop": (("start", "turn_on", "on"), ("stop", "turn_off", "off")),
        "enable_disable": (("enable", "turn_on", "on"), ("disable", "turn_off", "off")),
        "limit": (("limit", "set_value", None),),
        "current": (("current", "set_value", None),),
    }
    for field, ref in provider.get("command_entities", {}).items():
        for action, service, desired in routes.get(field, ()):
            result.pop(action, None)
            entity = er.async_get(hass).async_get(ref)
            domain = "switch" if field in {"start_stop", "enable_disable"} else "number"
            if (
                entity
                and entity.device_id == provider["device"]
                and not entity.disabled_by
                and entity.domain == domain
                and entity.platform != "ev_charge_manager"
                and hass.services.has_service(domain, service)
            ):
                result[action] = Capability(
                    provider["id"], provider["device"], entity.id, action, domain, service, desired
                )
    return result


def select_capability(hass, vehicle, action):
    """WRITE fallback selects before dispatch; execution never falls back/retries."""
    for provider in provider_order(vehicle, "write", action):
        capability = capabilities(hass, provider).get(action)
        if capability:
            return capability
    return None


class CommandExecutor:
    def __init__(self, hass, *, transport=None, budget=100, ttl=120, timeout_seconds=10):
        self.hass, self.transport = hass, transport
        self.budget, self.ttl, self.timeout_seconds = budget, ttl, timeout_seconds
        self.requests = 0
        self.records = {}
        self.locks = {}
        self.owners = {}
        self.pending = {}
        self.trace = []

    async def execute(self, key, target, context, value=None):
        async with self.locks.setdefault(target.device, Lock()):
            result = await self._execute(key, target, context, value)
            self.trace = [
                *self.trace[-49:],
                {"action": target.action, "status": result.status, "reason": result.reason},
            ]
            return result

    async def _execute(self, key, target, context, value):
        if self.transport is None:
            return Result("disabled", "No command transport configured")
        if (
            not context.session_id
            or context.session_id != context.current_session
            or not context.fresh
            or not context.authorized
            or not context.commissioned_charger
            or (not context.guest and not context.commissioned_vehicle)
            or context.owner not in {"brain", "optimizer", "manual"}
            or (context.guest and context.owner != "manual")
        ):
            return Result(
                "unsafe", "Fresh authorized physical session and per-device commissioning required"
            )
        registry = er.async_get(self.hass)
        entity = registry.async_get(target.registry_id)
        if (
            entity is None
            or entity.device_id != target.device
            or entity.disabled_by
            or entity.domain != target.domain
            or entity.platform == "ev_charge_manager"
            or dr.async_get(self.hass).async_get(target.device) is None
            or not self.hass.services.has_service(target.domain, target.service)
        ):
            return Result("unsupported", "Mapped capability is no longer available")
        # Do not trust constructed capabilities to bypass the supported route set.
        allowed = {
            "start": ("switch", "turn_on", "on"),
            "stop": ("switch", "turn_off", "off"),
            "enable": ("switch", "turn_on", "on"),
            "disable": ("switch", "turn_off", "off"),
            "limit": ("number", "set_value", None),
            "current": ("number", "set_value", None),
        }
        if allowed.get(target.action) != (target.domain, target.service, target.desired):
            return Result("unsupported", "Unreviewed service route")
        state = self.hass.states.get(entity.entity_id)
        now = dt_util.utcnow()
        if (
            not state
            or state.state in {"unknown", "unavailable"}
            or not 0 <= (now - state.last_reported).total_seconds() <= self.ttl
        ):
            return Result("stale", "Fresh read-before-write state required")
        desired = target.desired
        if target.domain == "number":
            try:
                lower, upper, step = (float(state.attributes[k]) for k in ("min", "max", "step"))
                if (
                    isinstance(value, bool)
                    or not isinstance(value, (float, int))
                    or not isfinite(value)
                    or not all(isfinite(v) for v in (lower, upper, step))
                    or step <= 0
                    or lower > upper
                    or not lower <= value <= upper
                    or (target.action == "limit" and not 0 <= value <= 100)
                    or (
                        target.action == "current"
                        and state.attributes.get("unit_of_measurement") != "A"
                    )
                    or abs((value - lower) / step - round((value - lower) / step)) > 1e-6
                ):
                    raise ValueError
                desired = str(float(value))
                current = str(float(state.state))
            except ValueError, TypeError, KeyError, OverflowError:
                return Result("invalid_value", "Reviewed device bounds, step and unit required")
        else:
            if value is not None:
                return Result("invalid_value", "Switch commands do not accept a numeric value")
            if state.state not in {"on", "off"}:
                return Result("stale", "Switch state must be on/off")
            current = state.state
        identity = (target, context.session_id, context.owner, value)
        prior = self.records.get(key)
        if prior and prior[0] != identity:
            return Result("idempotency_conflict")
        resource = (target.device, context.session_id)
        if self.owners.get(resource, context.owner) != context.owner:
            return Result("ownership_conflict")
        if prior:
            _, attempted_at, result = prior
            if current == desired and state.last_reported > attempted_at:
                result = replace(result, status="observed", reason="New matching entity report")
                self.records[key] = (identity, attempted_at, result)
                if self.pending.get(target.device) == key:
                    self.pending.pop(target.device)
            return result
        if target.device in self.pending:
            return Result(
                "resource_uncertain",
                "Reconcile the outstanding command; do not send an alternative",
            )
        if current == desired:
            return Result("already_observed", "No write needed")
        if self.requests >= self.budget:
            return Result("budget_exhausted")
        self.owners[resource] = context.owner
        self.pending[target.device] = key
        self.requests += 1
        payload = {"entity_id": entity.entity_id}
        if target.domain == "number":
            payload["value"] = value
        # Reserve idempotency/ownership before dispatch; even timeout is ambiguous.
        result = Result("uncertain", "Dispatch not yet observed")
        self.records[key] = (identity, now, result)
        try:
            async with timeout(self.timeout_seconds):
                await self.transport(target.domain, target.service, payload, blocking=True)
            result = Result("awaiting_observation", "Service return is not state confirmation")
        except (HomeAssistantError, TimeoutError, OSError) as error:
            result = Result("uncertain", type(error).__name__)
        self.records[key] = (identity, now, result)
        return result
