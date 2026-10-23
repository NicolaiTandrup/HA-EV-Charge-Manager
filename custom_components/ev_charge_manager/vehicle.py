"""Shared logical identity, semantic discovery and per-field provider fallback.

Only reads existing HA states: never refreshes a provider or wakes a vehicle.
Provider order is configured per logical vehicle, independent of vehicle names.
"""

from dataclasses import dataclass
from math import isfinite

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
    reported_at: object
    attributes: dict


class VehicleRegistry:
    def __init__(self, hass, vehicles, ttl=900):
        self.hass, self.vehicles, self.ttl = hass, vehicles, ttl

    def resolve(self, vehicle, field, now):
        """A valid fresh primary off/zero wins over fallback on/nonzero."""
        for provider in vehicle.get("providers", []):
            entity_id = provider.get("fields", {}).get(field)
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
