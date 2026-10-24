"""Read-only adapter for independent Energy Price Engine API v1.

No supplier, tariff, tax or VAT arithmetic and no price retrieval. Never substitute
legacy prices if the explicitly selected producer is unavailable.
"""

from dataclasses import dataclass
from datetime import timedelta
from importlib import import_module
from math import isfinite

from .planner import PriceSlot, utc

PRODUCER_DOMAIN = "ha_energy_price_engine"
REVISION_EVENT = f"{PRODUCER_DOMAIN}_price_revision_v1"


@dataclass(frozen=True)
class ConsumerPrices:
    status: str
    slots: tuple[PriceSlot, ...] = ()
    revision: int | None = None
    last_success: str | None = None
    reason: str | None = None


class PriceConsumer:
    def __init__(self, hass):
        self.hass = hass
        self.retry_at = None
        self.failures = 0

    def lookup(self, site_id, start, end, now):
        start, end, now = utc(start), utc(end), utc(now)
        if end <= start or start.timestamp() % 900 or end.timestamp() % 900:
            raise ValueError("Expected a positive quarter-aligned aware range")
        if self.retry_at and now < self.retry_at:
            return ConsumerPrices("NOT_LOADED", reason="Producer discovery backoff")
        try:
            api = import_module(f"custom_components.{PRODUCER_DOMAIN}.api").get_api(
                self.hass, version=1
            )
        except ImportError, LookupError, ValueError:
            self.failures += 1
            self.retry_at = now + timedelta(seconds=min(900, 30 * 2 ** min(self.failures - 1, 5)))
            return ConsumerPrices("NOT_LOADED", reason="Price Engine API v1 is not loaded")
        self.retry_at, self.failures = None, 0
        result = api.lookup(site_id, start, end, now=now)
        status = str(result.status)
        if status != "READY":
            return ConsumerPrices(
                status,
                revision=result.revision,
                last_success=result.last_success,
                reason=result.reason or "Producer prices are not ready",
            )
        rows = result.records
        expected = int((end - start).total_seconds() / 900)
        if (
            result.api_version != 1
            or result.site_id != site_id
            or len(rows) != expected
            or result.valid_slots != expected
            or result.expected_slots != expected
            or not rows
            or rows[0].start != start
            or rows[-1].end != end
            or any(a.end != b.start for a, b in zip(rows, rows[1:]))
            or any(
                r.site_id != site_id
                or r.currency != "DKK"
                or r.unit != "DKK/kWh"
                or r.end - r.start != timedelta(minutes=15)
                or not isfinite(r.final_price_incl_vat)
                for r in rows
            )
        ):
            return ConsumerPrices("ERROR", reason="Invalid producer range, site, unit or coverage")
        return ConsumerPrices(
            "READY",
            tuple(PriceSlot(r.start, r.end, r.final_price_incl_vat) for r in rows),
            result.revision,
            result.last_success,
        )

    def invalidate_discovery(self):
        self.retry_at = None
        self.failures = 0
