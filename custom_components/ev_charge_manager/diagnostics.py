"""Anonymous counts only; no IDs, VINs, locations or source attributes."""

from collections import Counter


async def async_get_config_entry_diagnostics(hass, entry):
    c = entry.runtime_data
    return {
        "schema_version": 1,
        "mode": "read_only",
        "vehicles": len(c.registry.vehicles),
        "sites": len(c.sites),
        "chargers": len(c.brain.sessions),
        "brain_enabled": c.config.get("brain_enabled", True),
        "optimizer_enabled": c.config.get("optimizer_enabled", True),
        "association_modes": dict(Counter(r["mode"] for r in c.data["assignments"].values())),
        "simulated_requests": c.commands.estimated_requests,
    }
