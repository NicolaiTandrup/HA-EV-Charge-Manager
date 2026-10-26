"""Stable charger source identity; raw legacy observations remain read-only."""

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .providers import adapter


def discover_status(hass, device):
    rows = [
        e.entity_id
        for e in er.async_entries_for_device(er.async_get(hass), device)
        if e.domain == "sensor"
        and adapter(e).semantic(e) in {"status", "charger_status"}
        and not e.disabled_by
        and e.platform != "ev_charge_manager"
    ]
    return rows[0] if len(rows) == 1 else None


class ChargerRegistry:
    def __init__(self, hass, chargers):
        self.hass, self.chargers = hass, chargers
        self.reconcile()

    def source(self, charger):
        if any(
            other is not charger
            and (
                other.get("device") == charger.get("device")
                if charger.get("device")
                else other["status"] == charger["status"]
            )
            for other in self.chargers
        ):
            return None
        if not charger.get("device"):
            # Preserved migration/reference entries cannot commission commands.
            return charger["status"]
        entity = er.async_get(self.hass).async_get(charger.get("status_ref", ""))
        if (
            entity is None
            or entity.device_id != charger["device"]
            or entity.disabled_by
            or entity.platform == "ev_charge_manager"
            or dr.async_get(self.hass).async_get(charger["device"]) is None
        ):
            return None
        return entity.entity_id

    def reconcile(self):
        changed = False
        for charger in self.chargers:
            if charger.get("device") and "status_ref" not in charger:
                row = er.async_get(self.hass).async_get(charger["status"])
                charger["status_ref"] = (
                    row.id if row and row.device_id == charger["device"] else None
                )
                changed = True
            current = self.source(charger)
            if current and current != charger["status"]:
                charger["status"] = current
                changed = True
        return changed
