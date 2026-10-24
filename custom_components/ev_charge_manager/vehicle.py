"""Shared logical identity, semantic discovery and per-field provider fallback.

Only reads existing HA states: never refreshes a provider or wakes a vehicle.
Provider order is configured per logical vehicle, independent of vehicle names.
"""

import re
from dataclasses import dataclass
from datetime import datetime
from math import isfinite

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

FIELDS = {"soc", "target", "cable", "tracker", "charging", "power", "odometer"}
TRANSLATIONS = {
    "soc": {"battery_level", "battery"},
    "target": {"charge_limit", "charge_limit_soc"},
    "cable": {"charge_cable_connected", "charger_connected"},
    "charging": {"charging"},
    "power": {"charging_power", "charge_power"},
    "odometer": {"odometer"},
}


def physical_keys(hass, device_id):
    """Exact registry VIN evidence only; no names, network reads or fuzzy merging.

    Absence of a VIN is unknown identity, not proof that two devices differ. Raw
    identifiers are used transiently for equality and never published in diagnostics.
    """
    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        return set()
    values = [
        value
        for domain, value in device.identifiers
        if domain in {"tesla", "tesla_custom", "tesla_fleet"}
    ]
    if (device.manufacturer or "").lower() == "tesla" and device.serial_number:
        values.append(device.serial_number)
    return {
        value.upper() for value in values if re.fullmatch(r"[A-HJ-NPR-Z0-9]{17}", value.upper())
    }


def discover(hass, device_id):
    """Suggest unambiguous semantics, never infer from display names or suffixes."""
    found = {field: [] for field in FIELDS}
    for entity in er.async_entries_for_device(er.async_get(hass), device_id):
        if entity.disabled_by:
            continue
        domain = entity.entity_id.split(".")[0]
        if domain == "device_tracker":
            found["tracker"].append(entity.entity_id)
        for field, keys in TRANSLATIONS.items():
            if entity.translation_key in keys:
                found[field].append(entity.entity_id)
    return {field: values[0] for field, values in found.items() if len(values) == 1}


@dataclass(frozen=True)
class FieldValue:
    value: str
    entity_id: str
    provider: str
    reported_at: datetime
    attributes: dict


def snapshot_health(fields, max_skew_seconds=120):
    """Check the fields used together by the planner without changing priority.

    Report-time agreement is only a conservative HA-side check, never proof of
    an atomic upstream snapshot. Idle power and odometer reports are excluded:
    providers often retain the last charging power while the car is stopped.
    """
    required = {"soc", "target", "cable", "tracker", "charging"}
    charging = fields.get("charging")
    if charging and charging.value == "on":
        required.add("power")
    missing = sorted(field for field in required if fields.get(field) is None)
    reports = [fields[field].reported_at for field in required if fields.get(field)]
    skew = (max(reports) - min(reports)).total_seconds() if reports else None
    issues = []
    if missing:
        issues.append("missing_required_fields")
    cable = fields.get("cable")
    if charging and charging.value == "on" and cable and cable.value == "off":
        issues.append("charging_while_disconnected")
    if skew is not None and skew > max_skew_seconds:
        issues.append("report_time_skew")
    return {
        "forecast_safe": not issues,
        "issues": issues,
        "missing_fields": missing,
        "report_skew_seconds": skew,
        "max_report_skew_seconds": max_skew_seconds,
    }


def provider_order(vehicle, direction, capability):
    """Independent policy, with legacy READ order preserved until configured.

    Missing explicitly preferred providers fail closed. Fallback is selection only,
    never permission to retry an ambiguous write with another integration.
    """
    providers = vehicle.get("providers", [])
    policy = vehicle.get("provider_policy", {})
    preferred = policy.get(f"{direction}_overrides", {}).get(capability) or policy.get(
        f"{direction}_provider"
    )
    if preferred:
        primary = next((p for p in providers if p["id"] == preferred), None)
        if primary is None:
            return []
        ordered = [primary, *(p for p in providers if p is not primary)]
    else:
        ordered = list(providers)
    fallback = policy.get(f"{direction}_fallback", direction == "read")
    return ordered if fallback else ordered[:1]


class VehicleRegistry:
    def __init__(self, hass, vehicles, ttl=900, snapshot_skew_seconds=120):
        self.hass, self.vehicles, self.ttl = hass, vehicles, ttl
        self.snapshot_skew_seconds = snapshot_skew_seconds
        self.reconcile()

    def source_entity(self, provider, field):
        ref = provider.get("entity_refs", {}).get(field)
        entity = er.async_get(self.hass).async_get(ref) if ref else None
        device = provider.get("device")
        if not device or not dr.async_get(self.hass).async_get(device):
            return None
        identities = physical_keys(self.hass, device)
        owners = {
            v["id"]
            for v in self.vehicles
            for p in v.get("providers", [])
            if p.get("device") == device
            or (identities and identities & physical_keys(self.hass, p.get("device")))
        }
        logical = next(
            (v for v in self.vehicles if any(p is provider for p in v.get("providers", []))), {}
        )
        logical_keys = set().union(
            *(physical_keys(self.hass, p.get("device")) for p in logical.get("providers", []))
        )
        if (
            len(logical_keys) > 1
            or len(owners) != 1
            or entity is None
            or entity.platform == "ev_charge_manager"
            or entity.id != ref
            or entity.device_id != device
            or entity.disabled_by
        ):
            return None
        return entity.entity_id

    def reconcile(self):
        """Pin legacy references once; never replace a missing bound registry ID."""
        changed = False
        registry = er.async_get(self.hass)
        for vehicle in self.vehicles:
            for provider in vehicle.get("providers", []):
                refs = provider.setdefault("entity_refs", {})
                for field, entity_id in provider.get("fields", {}).items():
                    if field not in refs:
                        entity = registry.async_get(entity_id)
                        refs[field] = (
                            entity.id
                            if entity and entity.device_id == provider.get("device")
                            else None
                        )
                        changed = True
                    current = self.source_entity(provider, field)
                    if current and current != entity_id:
                        provider["fields"][field] = current
                        changed = True
        return changed

    def assess(self, snapshots):
        return {
            key: snapshot_health(fields, self.snapshot_skew_seconds)
            for key, fields in snapshots.items()
        }

    def resolve(self, vehicle, field, now):
        """A valid fresh primary off/zero wins over fallback on/nonzero."""
        for provider in provider_order(vehicle, "read", field):
            entity_id = self.source_entity(provider, field)
            state = self.hass.states.get(entity_id) if entity_id else None
            if state is None or not 0 <= (now - state.last_reported).total_seconds() <= self.ttl:
                continue
            value = state.state
            if value.lower() in {"unknown", "unavailable", "none", ""}:
                continue
            if field in {"soc", "target", "power", "odometer"}:
                try:
                    number = float(value)
                    if not isfinite(number) or (
                        field in {"soc", "target"} and not 0 <= number <= 100
                    ):
                        continue
                    if field in {"power", "odometer"} and number < 0:
                        continue
                    if field == "power" and state.attributes.get("unit_of_measurement") not in {
                        "W",
                        "kW",
                    }:
                        continue
                except ValueError:
                    continue
            if field == "odometer" and state.attributes.get("unit_of_measurement") not in {
                "km",
                "mi",
            }:
                continue
            if field in {"cable", "charging"} and value not in {
                "on",
                "off",
                "charging",
                "stopped",
                "connected",
                "disconnected",
                "complete",
            }:
                continue
            if field in {"cable", "charging"}:
                value = "on" if value in {"on", "connected", "charging"} else "off"
            return FieldValue(
                value, entity_id, provider["id"], state.last_reported, dict(state.attributes)
            )
        return None

    def snapshot(self, now):
        return {
            v["id"]: {field: self.resolve(v, field, now) for field in FIELDS} for v in self.vehicles
        }
