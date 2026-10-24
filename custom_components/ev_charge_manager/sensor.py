"""Unified optional dashboard contract. No UI consumer is mandatory."""

from dataclasses import asdict

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .executor import capabilities


async def async_setup_entry(hass, entry, async_add_entities):
    c = entry.runtime_data
    entities = [ManagerSensor(c, "assignments"), ManagerSensor(c, "status")]
    entities.extend(ManagerSensor(c, "vehicle_state", vehicle=v["id"]) for v in c.registry.vehicles)
    entities.extend(
        PriceSensor(c, site.site, kind)
        for site in c.sites.values()
        if site.site.get("price_source") != "energy_price_engine"
        for kind in ("current_price", "next_price", "price_status")
    )
    for site in c.sites:
        for vehicle in c.registry.vehicles:
            for kind in (
                "forecast",
                "expected_finish",
                "expected_next_start",
                "expected_soc_at_0700",
            ):
                entities.append(ManagerSensor(c, kind, site, vehicle["id"]))
    entities.extend(
        MeasuredSensor(c, v["id"], kind, site_id)
        for site_id in c.sites
        for v in c.registry.vehicles
        for kind in ("energy_kwh", "cost", "unpriced_energy_kwh")
    )
    entities.extend(
        MeasuredSensor(c, v["id"], "distance_km")
        for v in c.registry.vehicles
        if any(p.get("fields", {}).get("odometer") for p in v.get("providers", []))
    )
    # Period sensors use recorded calendar buckets, never redistribute old totals.
    entities.extend(
        MeasuredSensor(c, item.vehicle, item.kind, item.site, period)
        for item in list(entities)
        if isinstance(item, MeasuredSensor)
        for period in ("day", "week", "month", "year")
    )
    async_add_entities(entities)


class ManagerSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator, kind, site=None, vehicle=None):
        super().__init__(coordinator)
        self.kind, self.site, self.vehicle = kind, site, vehicle
        self._attr_unique_id = (
            f"{coordinator.entry.entry_id}_{site or 'manager'}_{vehicle or 'all'}_{kind}"
        )
        self._attr_name = f"{site or ''} {kind.replace('_', ' ')}".strip()
        self._attr_device_info = {
            "identifiers": {(DOMAIN, f"{coordinator.entry.entry_id}_{vehicle or 'manager'}")},
            "name": next(
                (v["name"] for v in coordinator.registry.vehicles if v["id"] == vehicle),
                "EV Charge Manager",
            ),
            "manufacturer": "EV Charge Manager",
            "model": "Read-only preview",
        }
        if kind == "vehicle_state":
            self._attr_device_class = SensorDeviceClass.BATTERY
            self._attr_native_unit_of_measurement = "%"
        elif kind in {"expected_finish", "expected_next_start"}:
            self._attr_device_class = SensorDeviceClass.TIMESTAMP
        elif kind == "expected_soc_at_0700":
            self._attr_device_class = SensorDeviceClass.BATTERY
            self._attr_native_unit_of_measurement = "%"

    @property
    def forecast(self):
        return (
            (self.coordinator.data or {}).get("forecasts", {}).get(self.site, {}).get(self.vehicle)
        )

    @property
    def available(self):
        if not super().available:
            return False
        if self.kind == "vehicle_state":
            return bool(self.coordinator.data["vehicles"].get(self.vehicle, {}).get("soc"))
        if self.kind in {"assignments", "status"}:
            return True
        return self.forecast is not None and (
            self.kind == "forecast" or getattr(self.forecast, self.kind) is not None
        )

    @property
    def native_value(self):
        if self.kind == "vehicle_state":
            value = self.coordinator.data["vehicles"].get(self.vehicle, {}).get("soc")
            return float(value.value) if value else None
        if self.kind == "status":
            return "read_only"
        if self.kind == "assignments":
            return sum(r["valid"] for r in self.coordinator.data["assignments"].values())
        f = self.forecast
        return (f.status if self.kind == "forecast" else getattr(f, self.kind)) if f else None

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data
        attrs = {
            "schema_version": 1,
            "operating_mode": "read_only",
            "updated_at": data["updated_at"].isoformat(),
        }
        if self.kind == "vehicle_state":
            attrs.update(
                vehicle_id=self.vehicle,
                provider_policy=next(
                    (
                        v.get("provider_policy", {})
                        for v in self.coordinator.registry.vehicles
                        if v["id"] == self.vehicle
                    ),
                    {},
                ),
                command_capabilities={
                    p["id"]: {
                        "supported": sorted(capabilities(self.hass, p)),
                        "control_enabled": False,
                    }
                    for v in self.coordinator.registry.vehicles
                    if v["id"] == self.vehicle
                    for p in v.get("providers", [])
                },
                snapshot_health=data["vehicle_health"].get(self.vehicle),
                fields={
                    field: {
                        "value": value.value,
                        "provider": value.provider,
                        "entity_id": value.entity_id,
                        "reported_at": value.reported_at.isoformat(),
                    }
                    if value
                    else None
                    for field, value in data["vehicles"].get(self.vehicle, {}).items()
                },
            )
        elif self.kind == "assignments":
            attrs.update(chargers=list(data["assignments"].values()), sessions=data["sessions"])
        elif self.kind == "status":
            attrs.update(
                brain_enabled=self.coordinator.config.get("brain_enabled", True),
                optimizer_enabled=self.coordinator.config.get("optimizer_enabled", True),
                simulated_requests=self.coordinator.commands.estimated_requests,
                simulation_trace=self.coordinator.commands.trace,
                price_consumers=data.get("price_status", {}),
            )
        elif self.forecast:
            f = self.forecast
            site = self.coordinator.sites[self.site].site
            attrs["price_source"] = {
                "type": "official_nordpool" if site.get("nordpool_entry") else "entity",
                "entity_id": site.get("price_entity"),
                "area": site.get("area"),
                "currency": "DKK",
                "unit": "DKK/kWh",
                "basis": site.get("tariff", {}).get("mode", "all_in"),
            }
            attrs.update(
                vehicle_id=self.vehicle,
                provider_policy=next(
                    (
                        v.get("provider_policy", {})
                        for v in self.coordinator.registry.vehicles
                        if v["id"] == self.vehicle
                    ),
                    {},
                ),
                site_id=self.site,
                valid=f.valid,
                provisional=f.provisional,
                reason=f.reason,
                assumptions=f.assumptions,
                forecast_basis="proposed_schedule",
                selected_slots=[
                    {**asdict(a), "start": a.start.isoformat(), "end": a.end.isoformat()}
                    for a in f.allocations
                ],
            )
        return attrs


class PriceSensor(CoordinatorEntity, SensorEntity):
    """Read only persisted records; publishing a state never fetches/calculates."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator, site, kind):
        super().__init__(coordinator)
        self.site, self.kind = site, kind
        self._attr_name = f"{site['name']} {kind.replace('_', ' ')}"
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{site['id']}_{kind}"
        if kind != "price_status":
            self._attr_native_unit_of_measurement = "DKK/kWh"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.entry.entry_id + "_prices_" + site["id"])},
            "name": site["name"] + " prices",
            "manufacturer": "EV Charge Manager",
            "model": "Persistent all-in price table",
        }

    def records(self):
        from datetime import timedelta

        from homeassistant.util import dt as dt_util

        now = dt_util.utcnow()
        return now, self.coordinator.price_engine.lookup(
            self.site["id"], now, now + timedelta(days=2)
        )

    @property
    def native_value(self):
        if self.kind == "price_status":
            return self.coordinator.price_updater.status.get(self.site["id"], {}).get(
                "status", "INCOMPLETE"
            )
        now, records = self.records()
        matches = [
            r
            for r in records
            if (r.start <= now < r.end if self.kind == "current_price" else r.start > now)
        ]
        return matches[0].final_price_incl_vat if matches else None

    @property
    def extra_state_attributes(self):
        import json

        now, records = self.records()
        current = next((r for r in records if r.start <= now < r.end), None)

        def dso(record):
            parts = json.loads(record.components_json)
            return (
                parts.get("components", {})
                .get("dso", {})
                .get("ex_vat", parts.get("ex_vat", {}).get("dso"))
            )

        current_dso = dso(current) if current else None
        next_change = (
            next((r.start for r in records if r.start > now and dso(r) != current_dso), None)
            if current
            else None
        )
        return {
            "schema_version": 1,
            "mode": "read_only",
            **self.coordinator.price_updater.status.get(self.site["id"], {}),
            "revision": self.coordinator.price_engine.revisions.get(self.site["id"], 0),
            "components": json.loads(current.components_json) if current else None,
            "source": json.loads(current.source_json) if current else None,
            "slot_start": current.start.isoformat() if current else None,
            "slot_end": current.end.isoformat() if current else None,
            "current_dso_tariff_ex_vat": current_dso,
            "next_dso_change_at": next_change.isoformat() if next_change else None,
            "day_validation": self.coordinator.price_schedule.days.get(self.site["id"], {}),
        }


class MeasuredSensor(CoordinatorEntity, SensorEntity):
    """Actual observed totals; never derived from planned allocations."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, coordinator, vehicle, kind, site=None, period=None):
        super().__init__(coordinator)
        self.vehicle, self.kind, self.site, self.period = vehicle, kind, site, period
        labels = {
            "energy_kwh": ("Measured charging energy", SensorDeviceClass.ENERGY, "kWh"),
            "cost": ("Measured priced charging cost", SensorDeviceClass.MONETARY, "DKK"),
            "unpriced_energy_kwh": (
                "Unpriced measured charging energy",
                SensorDeviceClass.ENERGY,
                "kWh",
            ),
            "distance_km": ("Measured driven distance", SensorDeviceClass.DISTANCE, "km"),
        }
        name, device_class, unit = labels[kind]
        self._attr_name = (site + " " if site else "") + name
        self._attr_unique_id = (
            f"{coordinator.entry.entry_id}_{vehicle}_{site or 'vehicle'}_history_{kind}"
        )
        if period:
            self._attr_name += " " + period
            self._attr_unique_id += "_" + period
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = unit
        self._attr_state_class = (
            SensorStateClass.TOTAL
            if kind == "cost" or period
            else SensorStateClass.TOTAL_INCREASING
        )
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.entry.entry_id + "_" + vehicle)},
            "name": next(v["name"] for v in coordinator.registry.vehicles if v["id"] == vehicle),
            "manufacturer": "EV Charge Manager",
            "model": "Read-only preview",
        }

    @property
    def history(self):
        if self.site is None:
            return self.coordinator.distance_history.get(self.vehicle)
        return self.coordinator.sites[self.site].history.get(self.vehicle)

    @property
    def available(self):
        return super().available and self.history is not None

    @property
    def native_value(self):
        if not self.history:
            return None
        value = (
            self.history.period_total(self.kind, self.period, dt_util.utcnow())
            if self.period
            else getattr(self.history, self.kind)
        )
        return round(value, 6)

    @property
    def last_reset(self):
        return (
            self.history.period_start(self.period, dt_util.utcnow())
            if self.period and self.history
            else None
        )

    @property
    def extra_state_attributes(self):
        history = self.history
        now = dt_util.utcnow()
        unpriced = (
            history.period_total("unpriced_energy_kwh", self.period, now)
            if history and self.period
            else history.unpriced_energy_kwh
            if history
            else None
        )
        energy = (
            history.period_total("energy_kwh", self.period, now)
            if history and self.period
            else history.energy_kwh
            if history
            else None
        )
        return {
            "schema_version": 1,
            "calendar_period": self.period,
            "calendar_timezone": history.calendar_timezone if history else None,
            "calendar_coverage": "observed_buckets_only",
            "first_recorded_date": min(history.daily) if history and history.daily else None,
            "legacy_lifetime_not_redistributed": True,
            "basis": "measured_not_planned",
            "site_id": self.site,
            "vehicle_id": self.vehicle,
            "unpriced_energy_kwh": unpriced,
            "cost_coverage": ("partial" if unpriced else "priced" if energy else "no_samples")
            if history
            else "unavailable",
            "sampling_gap_limit_seconds": 180,
            "restart_extrapolation": False,
        }
