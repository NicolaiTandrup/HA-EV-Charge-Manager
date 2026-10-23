"""One shared registry and Brain, with independent per-site planners."""

import logging
from datetime import timedelta
from types import SimpleNamespace

from homeassistant.core import callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .adapters import parse_prices
from .brain import DISCONNECTED, Brain, Reading, normalize
from .command import CommandManager
from .const import DOMAIN
from .optimizer import OptimizerCoordinator
from .prices import OfficialPrices
from .sessions import Sessions
from .vehicle import VehicleRegistry

LOGGER = logging.getLogger(__name__)


class SiteOptimizer(OptimizerCoordinator):
    """Adapt shared fields into the upstream coordinator without duplicating identity."""

    def __init__(self, hass, entry, site, registry):
        super().__init__(hass, entry)
        self.registry = registry
        self.site = site
        self.config = {"currency": "DKK", "price_attribute": "slots", **site, "vehicles": []}
        self.store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.{site['id']}.rules")
        self.history_store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.{site['id']}.history")
        self.price_slots = None
        self.readings = {}
        self.snapshot_health = {}

    def _state(self, entity_id, now):
        if entity_id == "internal.prices":
            if self.price_slots is None:
                raise ValueError("Official price source unavailable")
            return SimpleNamespace(
                attributes={
                    "slots": [
                        {"start": s.start.isoformat(), "end": s.end.isoformat(), "price": s.price}
                        for s in self.price_slots
                    ]
                }
            )
        if entity_id.startswith("internal."):
            _, key, field = entity_id.split(".")
            health = self.snapshot_health.get(key, {})
            if health.get("issues"):
                raise ValueError("Vehicle snapshot inconsistent: " + ", ".join(health["issues"]))
            value = self.readings.get(key, {}).get(field)
            if value is None:
                raise ValueError(f"Missing fresh {field}")
            return SimpleNamespace(state=value.value, attributes=value.attributes)
        return super()._state(entity_id, now)

    def prepare(self, readings):
        self.readings = readings
        self.snapshot_health = self.registry.assess(readings)
        self.config["vehicles"] = [
            {
                "key": v["id"],
                "name": v["name"],
                "capacity_kwh": v["capacity_kwh"],
                "max_kw": v["max_kw"],
                "efficiency": v.get("efficiency", 1),
                "soc_entity": f"internal.{v['id']}.soc",
                "target_entity": f"internal.{v['id']}.target",
                "connected_entity": f"internal.{v['id']}.cable",
                "charging_entity": f"internal.{v['id']}.charging",
                "power_entity": f"internal.{v['id']}.power",
                "location_entity": f"internal.{v['id']}.tracker",
                "location_value": self.site["zone_state"],
            }
            for v in self.registry.vehicles
        ]


class ManagerCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry):
        super().__init__(
            hass, LOGGER, name=DOMAIN, config_entry=entry, update_interval=timedelta(seconds=15)
        )
        self.entry = entry
        self.config = {**entry.data, **entry.options}
        self.registry = VehicleRegistry(
            hass,
            self.config.get("vehicles", []),
            self.config.get("stale_seconds", 900),
            self.config.get("snapshot_skew_seconds", 120),
        )
        self.commands = CommandManager(self.config.get("command_budget", 100))
        self.store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.sessions")
        self.sessions = Sessions()
        self.prices = OfficialPrices(hass)
        vehicles = [
            {
                "id": v["id"],
                "name": v["name"],
                "cable": f"internal.{v['id']}.cable",
                "tracker": f"internal.{v['id']}.tracker",
            }
            for v in self.registry.vehicles
        ]
        self.brain = Brain(
            {
                "vehicles": vehicles,
                "chargers": self.config.get("chargers", []),
                "stale_seconds": self.registry.ttl,
            }
        )
        self.sites = (
            {
                s["id"]: SiteOptimizer(hass, entry, s, self.registry)
                for s in self.config.get("sites", [])
            }
            if self.config.get("optimizer_enabled", True)
            else {}
        )

    async def async_load(self):
        self.sessions = Sessions(await self.store.async_load())
        for site in self.sites.values():
            await site.async_load()

    async def async_save(self):
        await self.store.async_save(self.sessions.persistent())
        for site in self.sites.values():
            await site.async_save()

    @callback
    def async_listen(self):
        ids = {c["status"] for c in self.config.get("chargers", [])}
        ids.update(s["price_entity"] for s in self.config.get("sites", []) if s.get("price_entity"))
        for site in self.config.get("sites", []):
            ids.update(site[k] for k in ("guest_power_entity", "grid_tariff_entity") if site.get(k))
        for vehicle in self.registry.vehicles:
            for provider in vehicle.get("providers", []):
                ids.update(provider["fields"].values())
        if ids:
            self.entry.async_on_unload(
                async_track_state_change_event(self.hass, ids, self._changed)
            )

    @callback
    def _changed(self, event):
        # Capture unplug edges even when a rapid replug coalesces refresh requests.
        state = event.data.get("new_state")
        if state and normalize(state.state) in DISCONNECTED:
            for charger in self.config.get("chargers", []):
                if charger["status"] == event.data["entity_id"]:
                    self.sessions.items.pop(charger["id"], None)
                    session = self.brain.sessions[charger["id"]]
                    session.last_car = session.car or session.last_car
                    session.car = None
                    session.manual = False
        self.hass.async_create_task(self.async_request_refresh())

    async def _async_update_data(self):
        now = dt_util.utcnow()
        snapshots = self.registry.snapshot(now)
        states = {}
        for key, fields in snapshots.items():
            for field, value in fields.items():
                if value:
                    states[f"internal.{key}.{field}"] = Reading(value.value, value.reported_at)
        for charger in self.config.get("chargers", []):
            state = self.hass.states.get(charger["status"])
            if state:
                states[charger["status"]] = Reading(state.state, state.last_reported)
        rows = self.brain.evaluate(states, now) if self.config.get("brain_enabled", True) else {}
        session_rows = {}
        for charger in self.config.get("chargers", []):
            reading = states.get(charger["status"])
            status = (
                reading.value
                if reading and 0 <= (now - reading.reported_at).total_seconds() <= self.registry.ttl
                else None
            )
            row = rows.get(charger["id"], {})
            session = self.sessions.update(
                charger["id"],
                status,
                row.get("car") if row.get("valid") else None,
                now=now,
                reported_at=reading.reported_at if reading else None,
            )
            session_rows[charger["id"]] = {
                "session_id": session.id if session else None,
                "simulated_guest_authorized": session.authorized if session else False,
                "known_vehicle": session.vehicle if session else None,
                "charger_id": charger["id"],
                "session_start": session.started_at if session else None,
                "last_verified_connected": session.last_verified_connected if session else None,
                "authorization_source": (
                    "manual_guest"
                    if session.authorized
                    else "optimizer_known_car"
                    if session.vehicle and row.get("valid")
                    else "none"
                )
                if session
                else "none",
                "pending_action": None,
                "reason": "read_only_simulation_no_physical_permission_changed",
            }
        # If Brain is enabled, only fresh unique associations admit a managed car.
        admitted = {
            r["car"]
            for key, r in rows.items()
            if r["valid"] and not session_rows[key]["simulated_guest_authorized"]
        }
        forecasts = {}
        for key, site in self.sites.items():
            site.prepare(snapshots)
            if self.config.get("brain_enabled", True):
                site.config["vehicles"] = [
                    v for v in site.config["vehicles"] if v["key"] in admitted
                ]
            tariff = dict(site.site.get("tariff", {}))
            site.config["tariff"] = tariff
            site.config["grid_kw"] = site.site["grid_kw"]
            uncertain_guest = any(
                charger["zone_state"] == site.site["zone_state"]
                and charger["id"] in self.sessions.items
                and (
                    self.sessions.items[charger["id"]].authorized
                    or (
                        self.config.get("brain_enabled", True)
                        and not rows.get(charger["id"], {}).get("valid")
                    )
                )
                for charger in self.config.get("chargers", [])
            )
            if uncertain_guest and not site.site.get("guest_power_entity"):
                # Unknown consumption is not evidence of zero demand.
                site.config["grid_kw"] = 0
            try:
                if site.site.get("grid_tariff_entity"):
                    tariff_state = site._state(site.site["grid_tariff_entity"], now)
                    tariff["grid_slots"] = parse_prices(dict(tariff_state.attributes), "slots")
                if site.site.get("guest_power_entity"):
                    guest = site._state(site.site["guest_power_entity"], now)
                    power = float(guest.state)
                    from math import isfinite

                    if (
                        not isfinite(power)
                        or power < 0
                        or guest.attributes.get("unit_of_measurement") not in {"W", "kW"}
                    ):
                        raise ValueError("Guest demand requires finite W or kW")
                    power /= 1000 if guest.attributes["unit_of_measurement"] == "W" else 1
                    site.config["grid_kw"] = max(0, site.site["grid_kw"] - power)
            except ValueError, TypeError, KeyError:
                site.config["grid_kw"] = 0
            if site.site.get("nordpool_entry"):
                try:
                    site.price_slots = await self.prices.get({**site.site, "tariff": tariff}, now)
                except ValueError, TypeError, KeyError:
                    site.price_slots = []
                site.config["price_entity"] = "internal.prices"
                # Official prices already include the explicitly configured tariff.
                site.config["tariff"] = {"mode": "all_in"}
            forecasts[key] = await site._async_update_data()
        saved = self.sessions.persistent()
        self.store.async_delay_save(lambda: saved, 1)
        return {
            "vehicles": snapshots,
            "vehicle_health": self.registry.assess(snapshots),
            "assignments": rows,
            "sessions": session_rows,
            "forecasts": forecasts,
            "updated_at": now,
        }
