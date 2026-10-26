"""Provider profiles translate verified registry semantics, never entity names.

No vendor imports, polling, RPCs or automatic control authorization. Generic
semantics/manual overrides remain available for unsupported provider versions.
"""

import re


class GenericAdapter:
    domain = "generic"
    evidence = "HA registry translation key; manual review required"

    @classmethod
    def semantic(cls, entity):
        return entity.translation_key

    @classmethod
    def location(cls, entity):
        return entity.domain == "device_tracker"


class TeslaFleetAdapter(GenericAdapter):
    domain = "tesla_fleet"
    evidence = "Home Assistant 2026.10.2 Tesla Fleet entity descriptions"
    aliases = {
        "charge_state_battery_level": "battery_level",
        "charge_state_charge_limit_soc": "charge_limit_soc",
        "charge_state_conn_charge_cable": "charge_cable_connected",
        "charge_state_charger_power": "charging_power",
        "charge_state_charging_state": "charging",
        "charge_state_charge_current_request": "charge_current",
        "vehicle_state_odometer": "odometer",
    }

    @classmethod
    def semantic(cls, entity):
        return cls.aliases.get(entity.translation_key, entity.translation_key)

    @classmethod
    def location(cls, entity):
        return entity.domain == "device_tracker" and entity.translation_key == "location"


class TeslaCustomAdapter(GenericAdapter):
    domain = "tesla_custom"
    evidence = "alandtse/tesla 87010a33df0c6119c4134838dbd7253b6af5edeb"
    aliases = {
        ("sensor", "battery"): "battery",
        ("sensor", "charger_power"): "charging_power",
        ("sensor", "odometer"): "odometer",
        ("number", "charge_limit"): "charge_limit",
        ("number", "charging_amps"): "charge_current",
        ("binary_sensor", "charger"): "charge_cable_connected",
        ("binary_sensor", "charging"): "charging",
        ("switch", "charger"): "charging",
        ("device_tracker", "location_tracker"): "location",
    }

    @classmethod
    def semantic(cls, entity):
        if entity.translation_key:
            return entity.translation_key
        # Vendor's entire VIN+type unique-ID contract, not a display-name suffix.
        match = re.fullmatch(r"[a-hj-npr-z0-9]{17}_([a-z_]+)", entity.unique_id)
        return cls.aliases.get((entity.domain, match[1])) if match else None

    @classmethod
    def location(cls, entity):
        return entity.domain == "device_tracker" and cls.semantic(entity) == "location"


class EaseeAdapter(GenericAdapter):
    domain = "easee"
    evidence = "nordicopen/easee_hass 85dbd07d6b4e4059735ecd9c97b5569fb52347d0"

    @classmethod
    def semantic(cls, entity):
        return {"easee_status": "charger_status", "is_enabled": "charger_enabled"}.get(
            entity.translation_key, entity.translation_key
        )


ADAPTERS = {
    adapter.domain: adapter for adapter in (TeslaFleetAdapter, TeslaCustomAdapter, EaseeAdapter)
}


def adapter(entity):
    return ADAPTERS.get(entity.platform, GenericAdapter)
