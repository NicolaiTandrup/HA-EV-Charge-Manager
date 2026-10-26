"""Shared observation/planning eligibility. None of these policies grants control."""

from math import isfinite


def site_for(config, charger):
    selected = charger.get("site_id")
    if selected:
        return next(
            (
                s
                for s in config.get("sites", [])
                if s["id"] == selected and s["zone_state"] == charger["zone_state"]
            ),
            None,
        )
    return next(
        (s for s in config.get("sites", []) if s["zone_state"] == charger["zone_state"]), None
    )


def charger_enabled(config, charger):
    site = site_for(config, charger)
    power = charger.get("max_kw")
    valid_power = power is None or (
        not isinstance(power, bool)
        and isinstance(power, (int, float))
        and isfinite(power)
        and power > 0
    )
    return (
        valid_power
        and charger.get("enabled", True)
        and (not charger.get("site_id") or site is not None)
        and (site is None or site.get("enabled", True))
    )


def vehicle_at_site(vehicle, site):
    return vehicle.get("enabled", True) and (
        not vehicle.get("restrict_sites", False) or site["id"] in vehicle.get("allowed_sites", [])
    )


def eligible(config, vehicle, charger):
    site = site_for(config, charger)
    return (
        charger_enabled(config, charger)
        and vehicle.get("enabled", True)
        and (
            not charger.get("restrict_vehicles", False)
            or vehicle["id"] in charger.get("eligible_vehicles", [])
        )
        and (
            not vehicle.get("restrict_sites", False)
            or (site is not None and site["id"] in vehicle.get("allowed_sites", []))
        )
    )
