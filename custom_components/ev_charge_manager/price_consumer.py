"""Versioned read-only consumer. No market fetching, fees, VAT or price storage."""

from asyncio import Lock
from datetime import timedelta
from hashlib import sha256
from importlib import import_module
from math import isfinite
from zoneinfo import ZoneInfo

from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import HomeAssistantError

from .planner import PriceSlot, utc

DOMAIN = "ha_energy_price_engine"
EVENT = f"{DOMAIN}_price_revision_v1"


def decode(response, entry_id, site_id, now, start, end, max_age=129600):
    """Validate identity, conventions, freshness and intervals without arithmetic."""
    from datetime import datetime

    if (
        not isinstance(response, dict)
        or type(response.get("api_version")) is not int
        or response["api_version"] != 1
    ):
        raise ValueError("Unsupported producer API version")
    if response.get("producer_entry_id") != entry_id or response.get("site_id") != site_id:
        raise ValueError("Producer/site identity mismatch")
    if (response.get("currency"), response.get("unit"), response.get("vat_included")) != (
        "DKK",
        "DKK/kWh",
        True,
    ):
        raise ValueError("Explicit final inclusive DKK/kWh required")
    if type(response.get("revision")) is not int or response["revision"] < 0:
        raise ValueError("Invalid producer revision")
    if response.get("status") not in {"READY", "INCOMPLETE"}:
        raise ValueError("Producer not ready or stale")
    if response.get("vat_included") is not True:
        raise ValueError("VAT inclusion must be an explicit boolean")
    verified = utc(datetime.fromisoformat(response["verified_at"]))
    if not 0 <= (now - verified).total_seconds() <= max_age:
        raise ValueError("Producer verification stale or future-dated")
    raw = response.get("slots")
    if not isinstance(raw, list) or len(raw) > 1000:
        raise ValueError("Missing or oversized range response")
    slots = []
    previous = None
    for row in raw:
        a, b = utc(datetime.fromisoformat(row["start"])), utc(datetime.fromisoformat(row["end"]))
        amount = row["final_price_incl_vat"]
        if isinstance(amount, bool) or not isinstance(amount, (float, int)) or not isfinite(amount):
            raise ValueError("Invalid final price")
        if (
            a.timestamp() % 900
            or b - a != timedelta(minutes=15)
            or a < start
            or b > end
            or (previous is not None and a < previous)
        ):
            raise ValueError("Invalid, duplicate or out-of-range interval")
        slots.append(PriceSlot(a, b, amount))
        previous = b
    if response["status"] == "READY" and (
        not slots
        or slots[0].start != start
        or slots[-1].end != end
        or any(a.end != b.start for a, b in zip(slots, slots[1:]))
    ):
        raise ValueError("READY range is incomplete")
    return tuple(slots), verified


class PricesUnavailable(ValueError):
    """A correctly identified producer range is not operationally ready."""


class PriceConsumer:
    def __init__(self, hass):
        self.hass = hass
        self.tables = {}
        self.status = {}
        self.attempts = {}
        self.verified = {}
        self.keys = {}
        self.revisions = {}
        self.event_revisions = {}
        self.locks = {}

    async def refresh(self, site, now, *, force=False):
        async with self.locks.setdefault(site["id"], Lock()):
            return await self._refresh(site, now, force=force)

    async def _refresh(self, site, now, *, force=False):
        key = site["id"]
        if (
            not force
            and key in self.attempts
            and 0 <= (now - self.attempts[key]).total_seconds() < 60
        ):
            return False
        self.attempts[key] = now
        old = self.tables.get(key, ())
        try:
            start = (now - timedelta(minutes=3)).replace(second=0, microsecond=0)
            start = start.replace(minute=start.minute // 15 * 15)
            local = now.astimezone(ZoneInfo(site["timezone"]))
            end = utc(
                (local + timedelta(days=2)).replace(hour=0, minute=0, second=0, microsecond=0)
            )
            # Each local-date subrange must itself be READY. Tomorrow's missing
            # publication cannot invalidate verified today's prices or actual cost.
            slots, successes, revisions, unavailable, ranges = [], [], [], [], []
            cursor = start
            while cursor < end:
                local_cursor = cursor.astimezone(ZoneInfo(site["timezone"]))
                boundary = utc(
                    (local_cursor + timedelta(days=1)).replace(
                        hour=0, minute=0, second=0, microsecond=0
                    )
                )
                until = min(boundary, end)
                try:
                    rows, verified, response = self._lookup(site, cursor, until, now)
                except PricesUnavailable as error:
                    unavailable.append(str(error))
                else:
                    if response["revision"] < self.revisions.get(key, 0):
                        raise ValueError("Producer revision rollback")
                    slots.extend(rows)
                    successes.append(verified)
                    revisions.append(response["revision"])
                    ranges.append({"start": cursor.isoformat(), "end": until.isoformat()})
                cursor = until
            if not successes:
                raise ValueError("; ".join(unavailable) or "No verified price ranges")
            self.tables[key] = tuple(slots)
            self.verified[key] = min(successes)
            self.revisions[key] = max(revisions)
            self.keys[key] = sha256(str(tuple(slots)).encode()).hexdigest()
            self.status[key] = {
                "status": "INCOMPLETE" if unavailable else "READY",
                "revision": max(revisions),
                "verified_at": min(successes).isoformat(),
                "reason": "; ".join(unavailable) or None,
                "verified_ranges": ranges,
                "api_version": 1,
            }
        except (
            ValueError,
            TypeError,
            KeyError,
            AttributeError,
            ImportError,
            LookupError,
            HomeAssistantError,
            TimeoutError,
        ) as error:
            self.tables[key] = ()
            self.keys[key] = "unavailable"
            self.status[key] = {
                "status": "ERROR",
                "reason": str(error) or type(error).__name__,
                "api_version": 1,
            }
        return old != self.tables[key]

    def lookup(self, site, start, end, now):
        """Read the producer-owned API v1; never fetch, compose or persist prices."""
        return self._lookup(site, start, end, now)[0]

    def _lookup(self, site, start, end, now):
        entry = self.hass.config_entries.async_get_entry(site["producer_entry"])
        if entry is None or entry.domain != DOMAIN or entry.state != ConfigEntryState.LOADED:
            raise ValueError("Price producer not loaded")
        # API v1 site IDs are globally unique. Verify selected entry ownership
        # against its durable business configuration, never private runtime state.
        config = {**entry.data, **entry.options}
        if config.get("id") != site["producer_site"]:
            raise ValueError("Producer/site ownership mismatch")
        api = import_module(f"custom_components.{DOMAIN}.api").get_api(self.hass, version=1)
        result = api.lookup(
            site["producer_site"], start, end, now=now, producer_entry_id=entry.entry_id
        )
        if str(result.status) != "READY":
            raise PricesUnavailable(
                f"{result.status}: {result.reason or 'Producer prices not ready'}"
            )
        if result.producer_entry_id != entry.entry_id:
            raise ValueError("Producer result entry ownership mismatch")
        expected = int((end - start).total_seconds() / 900)
        if result.expected_slots != expected or result.valid_slots != expected:
            raise ValueError("Producer coverage count mismatch")
        if any(
            r.site_id != site["producer_site"] or r.currency != "DKK" or r.unit != "DKK/kWh"
            for r in result.records
        ):
            raise ValueError("Producer record site or unit mismatch")
        # Normalize the frozen API object for the existing strict range validator.
        # This dictionary is internal; it is not an HA service response contract.
        response = {
            "api_version": result.api_version,
            "producer_entry_id": entry.entry_id,
            "site_id": result.site_id,
            "currency": "DKK",
            "unit": "DKK/kWh",
            "vat_included": True,
            "revision": result.revision,
            "status": "READY",
            "verified_at": result.last_success,
            "slots": [
                {
                    "start": r.start.isoformat(),
                    "end": r.end.isoformat(),
                    "final_price_incl_vat": r.final_price_incl_vat,
                }
                for r in result.records
            ],
        }
        slots, verified = decode(
            response,
            entry.entry_id,
            site["producer_site"],
            now,
            start,
            end,
            site.get("price_max_age_seconds", 129600),
        )
        return slots, verified, response

    def slots(self, site, now):
        producer = self.hass.config_entries.async_get_entry(site["producer_entry"])
        if (
            producer is None
            or producer.domain != DOMAIN
            or producer.state != ConfigEntryState.LOADED
            or {**producer.data, **producer.options}.get("id") != site["producer_site"]
        ):
            self.tables[site["id"]] = ()
            self.keys[site["id"]] = "unavailable"
            self.status[site["id"]] = {
                "status": "ERROR",
                "reason": "Price producer not loaded",
                "api_version": 1,
            }
            return ()
        if self.status.get(site["id"], {}).get("status") == "ERROR":
            return ()
        verified = self.verified.get(site["id"])
        if verified is None or not 0 <= (now - verified).total_seconds() <= site.get(
            "price_max_age_seconds", 129600
        ):
            self.keys[site["id"]] = "unavailable"
            self.tables[site["id"]] = ()
            self.status[site["id"]] = {
                "status": "STALE",
                "reason": "Producer verification expired",
                "api_version": 1,
            }
            return ()
        return self.tables.get(site["id"], ())
