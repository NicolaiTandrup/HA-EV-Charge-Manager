"""Versioned read-only consumer. No market fetching, fees, VAT or price storage."""

from asyncio import Lock, timeout
from datetime import timedelta
from hashlib import sha256
from math import isfinite
from zoneinfo import ZoneInfo

from homeassistant.config_entries import ConfigEntryState
from homeassistant.exceptions import HomeAssistantError

from .planner import PriceSlot, utc

DOMAIN = "ha_energy_price_engine"
EVENT = f"{DOMAIN}_prices_updated"


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
            producer = site["producer_entry"]
            entry = self.hass.config_entries.async_get_entry(producer)
            if (
                entry is None
                or entry.domain != DOMAIN
                or entry.state != ConfigEntryState.LOADED
                or not self.hass.services.has_service(DOMAIN, "get_prices")
            ):
                raise ValueError("Price producer not loaded")
            start = (now - timedelta(minutes=3)).replace(second=0, microsecond=0)
            start = start.replace(minute=start.minute // 15 * 15)
            local = now.astimezone(ZoneInfo(site["timezone"]))
            end = utc(
                (local + timedelta(days=2)).replace(hour=0, minute=0, second=0, microsecond=0)
            )
            async with timeout(10):
                response = await self.hass.services.async_call(
                    DOMAIN,
                    "get_prices",
                    {
                        "api_version": 1,
                        "config_entry_id": producer,
                        "site_id": site["producer_site"],
                        "start": start.isoformat(),
                        "end": end.isoformat(),
                    },
                    blocking=True,
                    return_response=True,
                )
            slots, verified = decode(
                response,
                producer,
                site["producer_site"],
                now,
                start,
                end,
                site.get("price_max_age_seconds", 129600),
            )
            if response["revision"] < self.revisions.get(key, 0):
                raise ValueError("Producer revision rollback")
            self.tables[key] = slots
            self.verified[key] = verified
            self.revisions[key] = response["revision"]
            self.keys[key] = sha256(str(slots).encode()).hexdigest()
            self.status[key] = {
                "status": response["status"],
                "revision": response["revision"],
                "verified_at": verified.isoformat(),
                "reason": None,
                "api_version": 1,
            }
        except (ValueError, TypeError, KeyError, HomeAssistantError, TimeoutError) as error:
            self.tables[key] = ()
            self.keys[key] = "unavailable"
            self.status[key] = {
                "status": "ERROR",
                "reason": str(error) or type(error).__name__,
                "api_version": 1,
            }
        return old != self.tables[key]

    def slots(self, site, now):
        producer = self.hass.config_entries.async_get_entry(site["producer_entry"])
        if (
            producer is None
            or producer.domain != DOMAIN
            or producer.state != ConfigEntryState.LOADED
            or not self.hass.services.has_service(DOMAIN, "get_prices")
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
