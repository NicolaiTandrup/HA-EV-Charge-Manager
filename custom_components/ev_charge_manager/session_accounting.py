"""Immutable measured-delta attribution, not another meter or price engine."""

from asyncio import Lock
from copy import deepcopy
from datetime import date, datetime
from uuid import uuid4

from homeassistant.exceptions import HomeAssistantError

from .history import History
from .journal import CommandJournalStore, finish_verified_write
from .policies import site_for

KINDS = ("energy_kwh", "cost", "unpriced_energy_kwh")


class SessionAccounting:
    def __init__(self, hass, entry_id):
        self.hass = hass
        self.store = CommandJournalStore(
            hass, 1, f"ev_charge_manager.{entry_id}.session_accounting"
        )
        self.records, self.active = {}, {}
        self.loaded, self.storage_error = False, None
        self.revision, self.saved_revision = 0, 0
        self.lock = Lock()

    async def async_load(self):
        try:
            data = await self.store.async_load()
            records = {}
            if data is not None:
                if (
                    not isinstance(data, dict)
                    or type(data.get("schema_version")) is not int
                    or data["schema_version"] != 1
                    or not isinstance(data.get("records"), dict)
                ):
                    raise ValueError("Invalid session accounting")
                records = deepcopy(data["records"])
                for key, row in records.items():
                    if row["id"] != key or not row["charger_id"] or not row["physical_session_id"]:
                        raise ValueError("Invalid session identity")
                    for stamp in (
                        row["observed_from"],
                        row["last_observed_at"],
                        row.get("ended_at"),
                    ):
                        if stamp is not None and datetime.fromisoformat(stamp).tzinfo is None:
                            raise ValueError("Aware observation timestamps required")
                    History(**row["totals"])
                    if not isinstance(row["sample_days"], dict) or not isinstance(
                        row["price_evidence"], dict
                    ):
                        raise ValueError("Invalid measurement provenance")
                    for day, count in row["sample_days"].items():
                        date.fromisoformat(day)
                        if type(count) is not int or count < 0:
                            raise ValueError("Invalid measured day coverage")
                    if type(row["measured_intervals"]) is not int or row["measured_intervals"] < 0:
                        raise ValueError("Invalid measured coverage")
                    if row.get("ended_at") is None:
                        row["ended_at"] = row["last_observed_at"]
                        row["ended_reason"] = "restart_unverified"
            self.records, self.active = records, {}
            self.loaded, self.storage_error = True, None
            self.revision += 1
        except OSError, HomeAssistantError, ValueError, TypeError, KeyError:
            self.storage_error = "Unable to verify observed session accounting"
            self.loaded = False

    def reconcile(self, sessions, chargers, sites, now):
        if not self.loaded or self.storage_error:
            return
        config = {"sites": sites}
        charger_map = {c["id"]: c for c in chargers}
        for physical, key in list(self.active.items()):
            row = self.records[key]
            current = sessions.get(row["charger_id"])
            if current is None or current.id != physical:
                row["ended_at"] = now.isoformat()
                row["ended_reason"] = (
                    "configuration_removed"
                    if row["charger_id"] not in charger_map
                    else "connection_boundary"
                )
                self.active.pop(physical)
                self.revision += 1
        for charger_id, session in sessions.items():
            if charger_id not in charger_map:
                continue
            site = site_for(config, charger_map[charger_id])
            site_id = site["id"] if site else None
            identity = (charger_id, session.vehicle, site_id, session.source_device)
            key = self.active.get(session.id)
            if key:
                row = self.records[key]
                if (
                    row["charger_id"],
                    row["vehicle_id"],
                    row["site_id"],
                    row.get("source_device"),
                ) != identity:
                    row["ended_at"], row["ended_reason"] = now.isoformat(), "association_boundary"
                    self.active.pop(session.id)
                    self.revision += 1
                    key = None
            if key is None:
                key = uuid4().hex
                row = {
                    "id": key,
                    "physical_session_id": session.id,
                    "charger_id": charger_id,
                    "source_device": session.source_device,
                    "vehicle_id": session.vehicle,
                    "site_id": site_id,
                    "observed_from": now.isoformat(),
                    "last_observed_at": now.isoformat(),
                    "ended_at": None,
                    "ended_reason": None,
                    "measured_intervals": 0,
                    "basis": "vehicle_power_trapezoid_estimate"
                    if session.vehicle
                    else "unmeasured_unknown_vehicle",
                    "totals": History(
                        calendar_timezone=site["timezone"] if site else self.hass.config.time_zone
                    ).persistent(),
                    "price_evidence": {},
                    "sample_days": {},
                }
                self.records[key], self.active[session.id] = row, key
                self.revision += 1
            reported = session.last_verified_connected
            if reported and datetime.fromisoformat(reported) > datetime.fromisoformat(
                row["last_observed_at"]
            ):
                row["last_observed_at"] = reported
                self.revision += 1

    def active_for(self, charger_id):
        return next(
            (
                self.records[key]
                for key in self.active.values()
                if self.records[key]["charger_id"] == charger_id
            ),
            None,
        )

    def add(
        self,
        key,
        amounts,
        daily,
        sampled_at,
        source,
        prices,
        *,
        calendar_timezone=None,
        price_provenance=None,
    ):
        if not self.loaded or self.storage_error or key not in self.records:
            return
        row = self.records[key]
        if row["ended_at"] is not None:
            raise ValueError("Closed observation segments are immutable")
        totals = deepcopy(row["totals"])
        if calendar_timezone:
            if row["measured_intervals"] and totals["calendar_timezone"] != calendar_timezone:
                raise ValueError("Accounting calendar changed inside an observation segment")
            totals["calendar_timezone"] = calendar_timezone
        for kind in KINDS:
            totals[kind] += amounts[kind]
        for day, values in daily.items():
            target = totals["daily"].setdefault(day, {})
            for kind in KINDS:
                target[kind] = target.get(kind, 0) + values.get(kind, 0)
        History(**totals)  # Validate before mutation; negative cost remains a credit.
        row["totals"] = totals
        row["measured_intervals"] += 1
        if sampled_at > datetime.fromisoformat(row["last_observed_at"]):
            row["last_observed_at"] = sampled_at.isoformat()
        row["last_sample_at"], row["source_registry_reference"] = sampled_at.isoformat(), source
        for day in daily:
            row["sample_days"][day] = row["sample_days"].get(day, 0) + 1
        if not amounts["unpriced_energy_kwh"] and amounts["energy_kwh"] > 0:
            for price in prices:
                row["price_evidence"].setdefault(
                    price.start.isoformat() + "|" + str(price.price),
                    {
                        **(price_provenance or {}),
                        "start": price.start.isoformat(),
                        "end": price.end.isoformat(),
                        "final_price_incl_vat": price.price,
                        "currency": "DKK",
                        "unit": "DKK/kWh",
                    },
                )
        self.revision += 1

    def totals_for(self, charger_id, period, now):
        result = {kind: 0 for kind in KINDS}
        result["measured_intervals"] = 0
        result["unmeasured_segments"] = 0
        for row in self.records.values():
            if row["charger_id"] != charger_id:
                continue
            history = History(**row["totals"])
            for kind in KINDS:
                result[kind] += (
                    history.period_total(kind, period, now) if period else getattr(history, kind)
                )
            if period:
                first = str(history.period_start(period, now).date())
                last = str(history.period_start("day", now).date())
                result["measured_intervals"] += sum(
                    n for day, n in row["sample_days"].items() if first <= day <= last
                )
            else:
                result["measured_intervals"] += row["measured_intervals"]
            result["unmeasured_segments"] += row["measured_intervals"] == 0
        return result

    async def async_save(self):
        if not self.loaded or self.storage_error:
            return
        async with self.lock:
            if self.saved_revision == self.revision:
                return
            revision = self.revision
            data = {"schema_version": 1, "records": deepcopy(self.records)}
            try:
                await finish_verified_write(self.hass, self.store.async_save(data))
                self.saved_revision = revision
            except OSError, HomeAssistantError, ValueError, TypeError:
                self.storage_error = "Unable to persist observed session accounting"
