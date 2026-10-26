"""One shared registry and Brain, with independent per-site planners."""

import logging
from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace

from homeassistant.const import EVENT_STATE_CHANGED
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .brain import DISCONNECTED, Brain, Reading, normalize
from .chargers import ChargerRegistry
from .command import CommandManager
from .const import DOMAIN
from .history import History
from .journal import CommandJournalStore, DurableCommandExecutor
from .optimizer import OptimizerCoordinator
from .policies import charger_enabled, eligible, vehicle_at_site
from .price_consumer import EVENT as PRICE_EVENT
from .price_consumer import PriceConsumer
from .price_engine import PriceEngine
from .price_schedule import PriceSchedule
from .price_update import PriceUpdater
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
        self.price_slots = ()
        self.readings = {}
        self.snapshot_health = {}
        self.plan_key = None
        self.cached_plan = {}
        self.planned_at = None
        self.price_key = None
        self.price_error = None
        self.measurement_vehicles = None
        self.measurement_sources = {}

    def _plan(self, vehicles, slots, now, **kwargs):
        # Regular 30-minute cadence, with immediate input/price/safety-boundary
        # invalidation. History sampling/freshness checks still run every watchdog.
        key = (
            tuple(vehicles),
            self.price_key,
            int(now.timestamp() // 1800),
            tuple((k, v) for k, v in kwargs.items() if k != "states"),
        )
        crossed = False
        if self.planned_at:
            points = [
                point
                for forecast in self.cached_plan.values()
                for allocation in forecast.allocations
                for point in (allocation.start, allocation.end)
            ]
            points += [r.deadline for r in kwargs.get("states", {}).values() if r.deadline]
            crossed = any(self.planned_at < point <= now for point in points)
        if key != self.plan_key or crossed:
            self.cached_plan = super()._plan(vehicles, slots, now, **kwargs)
            self.plan_key, self.planned_at = key, now
        return dict(self.cached_plan)

    def _sample_history(self, vehicles, slots, now):
        # Actual power does not require SoC, target or a successful plan.
        for vehicle in self.registry.vehicles:
            key = vehicle["id"]
            fields = self.readings.get(key, {})
            selected = [fields.get(role) for role in ("cable", "charging", "power")]
            eligible = all(selected)
            power = 0
            if eligible:
                cable, charging, reading = selected
                reports = [value.reported_at for value in selected]
                eligible = (
                    cable.value == "on"
                    and charging.value == "on"
                    and (max(reports) - min(reports)).total_seconds()
                    <= self.registry.snapshot_skew_seconds
                )
                power = float(reading.value) / (
                    1000 if reading.attributes["unit_of_measurement"] == "W" else 1
                )
            if self.measurement_vehicles is None:
                tracker = fields.get("tracker")
                eligible = (
                    eligible and tracker is not None and tracker.value == self.site["zone_state"]
                )
            else:
                eligible = eligible and key in self.measurement_vehicles
            history = self.history.setdefault(key, History())
            sampled_at = now
            if eligible:
                provider = next(p for p in vehicle["providers"] if p["id"] == reading.provider)
                source_id = reading.provider + ":" + provider["entity_refs"]["power"]
                if self.measurement_sources.get(key) != source_id:
                    history.was_eligible = False
                self.measurement_sources[key] = source_id
                sampled_at = reading.reported_at
                if history.sampled_at is not None and sampled_at <= history.sampled_at:
                    continue  # Watchdog reads are not new physical measurements.
            history.sample_power(sampled_at, power, eligible, slots, timezone=self.site["timezone"])
        saved = {key: history.persistent() for key, history in self.history.items()}
        self.history_store.async_delay_save(lambda: saved, 1)

    def _prices(self, now):
        if self.price_error:
            raise ValueError(self.price_error)
        return self.price_slots

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
                **({"deadline_entity": v["deadline_entity"]} if v.get("deadline_entity") else {}),
                "soc_entity": f"internal.{v['id']}.soc",
                "target_entity": f"internal.{v['id']}.target",
                "connected_entity": f"internal.{v['id']}.cable",
                "charging_entity": f"internal.{v['id']}.charging",
                "power_entity": f"internal.{v['id']}.power",
                "location_entity": f"internal.{v['id']}.tracker",
                "location_value": self.site["zone_state"],
            }
            for v in self.registry.vehicles
            if vehicle_at_site(v, self.site)
        ]


class ManagerCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry):
        super().__init__(
            hass, LOGGER, name=DOMAIN, config_entry=entry, update_interval=timedelta(seconds=15)
        )
        self.entry = entry
        self.config = deepcopy({**entry.data, **entry.options})
        self.registry = VehicleRegistry(
            hass,
            self.config.get("vehicles", []),
            self.config.get("stale_seconds", 900),
            self.config.get("snapshot_skew_seconds", 120),
        )
        self.chargers = ChargerRegistry(hass, self.config.get("chargers", []))
        self.commands = CommandManager(self.config.get("command_budget", 100))
        self.executor = DurableCommandExecutor(
            hass,
            store=CommandJournalStore(hass, 1, f"{DOMAIN}.{entry.entry_id}.command_journal"),
            budget=self.config.get("command_budget", 100),
        )
        self.store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.sessions")
        self.sessions = Sessions()
        self.distance_store = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}.distance")
        self.distance_history = {}
        self.price_consumer = PriceConsumer(hass)
        self.price_engine = PriceEngine(hass, entry.entry_id)
        self.price_updater = PriceUpdater(hass, self.price_engine)
        self.price_schedule = PriceSchedule(self)
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
                "chargers": [
                    {
                        **c,
                        "enabled": charger_enabled(self.config, c),
                        "allowed_vehicles": [
                            v["id"] for v in self.registry.vehicles if eligible(self.config, v, c)
                        ],
                    }
                    for c in self.config.get("chargers", [])
                ],
                "stale_seconds": self.registry.ttl,
            }
        )
        self.sites = (
            {
                s["id"]: SiteOptimizer(hass, entry, s, self.registry)
                for s in self.config.get("sites", [])
                if s.get("enabled", True)
            }
            if self.config.get("optimizer_enabled", True)
            else {}
        )

    def persist_sources(self):
        target = "options" if self.entry.options else "data"
        values = dict(getattr(self.entry, target))
        values["vehicles"] = deepcopy(self.registry.vehicles)
        values["chargers"] = deepcopy(self.config.get("chargers", []))
        self.hass.config_entries.async_update_entry(self.entry, **{target: values})

    async def async_load(self):
        await self.executor.async_load()
        self.persist_sources()
        for key, record in (await self.distance_store.async_load() or {}).items():
            try:
                self.distance_history[key] = History(**record)
            except ValueError, TypeError:
                LOGGER.warning("Ignoring invalid persisted distance total")
        await self.price_engine.async_load(
            [
                k
                for k, s in self.sites.items()
                if s.site.get("price_source") != "energy_price_engine"
            ]
        )
        await self.price_updater.tariffs.load()
        await self.price_schedule.startup()
        for site in self.sites.values():
            if site.site.get("price_source") == "energy_price_engine":
                await self.price_consumer.refresh(site.site, dt_util.utcnow())
        saved_sessions = await self.store.async_load() or {}
        charger_ids = {c["id"] for c in self.config.get("chargers", [])}
        self.sessions = Sessions(
            {key: value for key, value in saved_sessions.items() if key in charger_ids}
        )
        vehicle_ids = {v["id"] for v in self.registry.vehicles}
        for session in self.sessions.items.values():
            if session.vehicle not in vehicle_ids:
                session.vehicle = None
                session.authorized = False
        for site in self.sites.values():
            await site.async_load()

    async def async_refresh_prices(self):
        now = dt_util.utcnow()
        for site in self.sites.values():
            if site.site.get("price_source") == "energy_price_engine":
                await self.price_consumer.refresh(site.site, now)
            else:
                await self.price_updater.refresh(site.site, now)

    async def _price_changed(self):
        await self.async_refresh_prices()
        await self.async_request_refresh()

    async def async_save(self):
        await self.store.async_save(self.sessions.persistent())
        await self.distance_store.async_save(
            {key: h.persistent() for key, h in self.distance_history.items()}
        )
        for site in self.sites.values():
            await site.async_save()

    @callback
    def _source_ids(self):
        ids = {c["status"] for c in self.config.get("chargers", [])}
        ids.update(s["price_entity"] for s in self.config.get("sites", []) if s.get("price_entity"))
        for site in self.config.get("sites", []):
            ids.update(site[k] for k in ("guest_power_entity", "grid_tariff_entity") if site.get(k))
        for vehicle in self.registry.vehicles:
            if vehicle.get("deadline_entity"):
                ids.add(vehicle["deadline_entity"])
            for provider in vehicle.get("providers", []):
                ids.update(provider["fields"].values())
        return ids

    @callback
    def async_listen(self):
        if any(s.site.get("price_source") != "energy_price_engine" for s in self.sites.values()):
            self.price_schedule.listen()
        self.entry.async_on_unload(self.hass.bus.async_listen(PRICE_EVENT, self._producer_changed))
        self.entry.async_on_unload(self.hass.bus.async_listen(EVENT_STATE_CHANGED, self._changed))
        self.entry.async_on_unload(
            self.hass.bus.async_listen(er.EVENT_ENTITY_REGISTRY_UPDATED, self._registry_changed)
        )

    @callback
    def _producer_changed(self, event):
        data = event.data
        if (
            type(data.get("api_version")) is not int
            or data.get("api_version") != 1
            or type(data.get("revision")) is not int
            or data["revision"] < 0
        ):
            return
        for site in self.sites.values():
            if site.site.get("price_source") == "energy_price_engine" and data.get(
                "site_id"
            ) == site.site.get("producer_site"):
                if data["revision"] > max(
                    self.price_consumer.revisions.get(site.site["id"], -1),
                    self.price_consumer.event_revisions.get(site.site["id"], -1),
                ):
                    self.price_consumer.event_revisions[site.site["id"]] = data["revision"]
                    self.entry.async_create_task(
                        self.hass, self._refresh_producer(site.site), "Read producer price revision"
                    )

    async def _refresh_producer(self, site):
        if await self.price_consumer.refresh(site, dt_util.utcnow(), force=True):
            await self.async_request_refresh()

    @callback
    def _registry_changed(self, event):
        vehicles_changed = self.registry.reconcile()
        chargers_changed = self.chargers.reconcile()
        if vehicles_changed or chargers_changed:
            self.persist_sources()
        self.entry.async_create_task(
            self.hass, self.async_request_refresh(), "Refresh managed snapshots"
        )

    @callback
    def _changed(self, event):
        if event.data["entity_id"] not in self._source_ids():
            return
        if event.data["entity_id"] in {
            s[k]
            for s in self.config.get("sites", [])
            for k in ("price_entity", "grid_tariff_entity")
            if s.get(k)
        }:
            source = er.async_get(self.hass).async_get(event.data["entity_id"])
            if source is None or source.platform != DOMAIN:
                self.entry.async_create_task(
                    self.hass, self._price_changed(), "Update price sources"
                )
            return
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
                    session.reviewed = False
        self.entry.async_create_task(
            self.hass, self.async_request_refresh(), "Refresh managed snapshots"
        )

    async def _async_update_data(self):
        now = dt_util.utcnow()
        snapshots = self.registry.snapshot(now)
        for vehicle in self.registry.vehicles:
            value = snapshots[vehicle["id"]].get("odometer")
            if value:
                provider = next(p for p in vehicle["providers"] if p["id"] == value.provider)
                stable_source = value.provider + ":" + provider["entity_refs"]["odometer"]
                history = self.distance_history.setdefault(vehicle["id"], History())
                history.sample_odometer(
                    stable_source,
                    float(value.value),
                    value.attributes.get("unit_of_measurement"),
                    now=value.reported_at,
                    timezone=self.hass.config.time_zone,
                )
        distance_saved = {key: h.persistent() for key, h in self.distance_history.items()}
        self.distance_store.async_delay_save(lambda: distance_saved, 1)
        states = {}
        for key, fields in snapshots.items():
            for field, value in fields.items():
                if value:
                    states[f"internal.{key}.{field}"] = Reading(value.value, value.reported_at)
        for charger in self.config.get("chargers", []):
            source = self.chargers.source(charger)
            state = self.hass.states.get(source) if source else None
            if state:
                states[charger["status"]] = Reading(state.state, state.last_reported)
        for brain_charger in self.brain.config["chargers"]:
            original = next(c for c in self.config["chargers"] if c["id"] == brain_charger["id"])
            brain_charger["status"] = original["status"]
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
                source_device=charger.get("device"),
            )
            session_rows[charger["id"]] = {
                "reported_status": normalize(status) if status else None,
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
            site.measurement_vehicles = None
            if self.config.get("brain_enabled", True):
                site.measurement_vehicles = {
                    row["car"]
                    for charger in self.config.get("chargers", [])
                    for row in [rows.get(charger["id"], {})]
                    if row.get("valid")
                    and charger["zone_state"] == site.site["zone_state"]
                    and not session_rows[charger["id"]]["simulated_guest_authorized"]
                }
            if self.config.get("brain_enabled", True):
                site.config["vehicles"] = [
                    v
                    for v in site.config["vehicles"]
                    if v["key"] in admitted
                    and any(
                        row.get("valid")
                        and row.get("car") == v["key"]
                        and charger["zone_state"] == site.site["zone_state"]
                        for charger in self.config.get("chargers", [])
                        for row in [rows.get(charger["id"], {})]
                    )
                ]
            for mapping in site.config["vehicles"]:
                caps = [
                    c["max_kw"]
                    for c in self.config.get("chargers", [])
                    if c.get("max_kw") is not None
                    and rows.get(c["id"], {}).get("valid")
                    and rows[c["id"]].get("car") == mapping["key"]
                ]
                if caps:
                    mapping["max_kw"] = min(mapping["max_kw"], *caps)
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
            if site.site.get("price_source") == "energy_price_engine":
                await self.price_consumer.refresh(site.site, now)
                site.price_slots = self.price_consumer.slots(site.site, now)
                site.price_key = self.price_consumer.keys.get(key)
                report = self.price_consumer.status.get(key, {})
                site.price_error = (
                    report.get("reason") if report.get("status") in {"ERROR", "STALE"} else None
                )
            else:
                site.price_key = self.price_engine.price_keys.get(key)
                site.price_slots = self.price_engine.slots(
                    key, now - timedelta(minutes=3), now + timedelta(days=3)
                )
            forecasts[key] = await site._async_update_data()
        saved = self.sessions.persistent()
        self.store.async_delay_save(lambda: saved, 1)
        return {
            "vehicles": snapshots,
            "vehicle_health": self.registry.assess(snapshots),
            "price_status": {**self.price_updater.status, **self.price_consumer.status},
            "assignments": rows,
            "sessions": session_rows,
            "forecasts": forecasts,
            "updated_at": now,
        }
