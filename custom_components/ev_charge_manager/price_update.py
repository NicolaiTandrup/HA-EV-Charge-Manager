"""Source refresh/composition boundary, separate from all lookup consumers."""

from asyncio import Lock
from zoneinfo import ZoneInfo

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from .adapters import parse_prices
from .price_engine import day_bounds
from .prices import OfficialPrices


class PriceUpdater:
    def __init__(self, hass, engine):
        self.hass, self.engine = hass, engine
        self.official = OfficialPrices(hass)
        self.status = {}
        self.lock = Lock()

    def state(self, entity_id, now, minutes):
        entry = er.async_get(self.hass).async_get(entity_id)
        if entry and entry.platform == "ev_charge_manager":
            raise ValueError("Integration output cannot be its own price source")
        state = self.hass.states.get(entity_id)
        if (
            state is None
            or state.state in {"unknown", "unavailable", ""}
            or not 0 <= (now - state.last_reported).total_seconds() <= minutes * 60
        ):
            raise ValueError("Price/tariff source missing or stale")
        return state

    async def refresh(self, site, now, *, force=False, dates=None):
        async with self.lock:
            key = site["id"]
            old = self.status.get(key, {})
            report = {**old, "last_attempt": now.isoformat(), "status": "ERROR"}
            self.status[key] = report
            try:
                tariff = dict(site.get("tariff", {}))
                if site.get("grid_tariff_entity"):
                    state = self.state(
                        site["grid_tariff_entity"], now, site.get("stale_minutes", 40)
                    )
                    tariff["grid_slots"] = parse_prices(dict(state.attributes), "slots")
                if site.get("nordpool_entry"):
                    slots = await self.official.get(
                        site, now, compose=False, force=force, dates=dates
                    )
                    source = {
                        "kind": "nordpool",
                        "config_entry": site["nordpool_entry"],
                        "area": site.get("area", "DK2"),
                        "input_unit": "DKK/MWh",
                        "input_vat": "excluded",
                    }
                else:
                    state = self.state(site["price_entity"], now, site.get("stale_minutes", 40))
                    slots = parse_prices(
                        dict(state.attributes),
                        site.get("price_attribute", "slots"),
                        site.get("price_multiplier", 1),
                    )
                    source = {
                        "kind": "entity",
                        "entity_id": site["price_entity"],
                        "multiplier": site.get("price_multiplier", 1),
                        "input_vat": tariff.get("mode", "all_in"),
                    }
                if site.get("nordpool_entry"):
                    times = [
                        timestamp
                        for (entry, area, _), (timestamp, data) in self.official.cache.items()
                        if entry == site["nordpool_entry"]
                        and area == site.get("area", "DK2")
                        and data
                    ]
                    source["verified_at"] = min(times).isoformat() if times else now.isoformat()
                else:
                    source["verified_at"] = state.last_reported.isoformat()
                if dates and site.get("nordpool_entry"):
                    for day in dates:
                        start, end = day_bounds(day, site["timezone"])
                        selected = [s for s in slots if start <= s.start and s.end <= end]
                        complete = (
                            bool(selected)
                            and selected[0].start == start
                            and selected[-1].end == end
                            and all(a.end == b.start for a, b in zip(selected, selected[1:]))
                        )
                        if not complete:
                            report.update(
                                status="INCOMPLETE",
                                reason="Requested day source series is incomplete",
                                changed=False,
                            )
                            return False
                changed = await self.engine.async_update(key, slots, tariff, source, now)
                day = now.astimezone(ZoneInfo(site["timezone"])).date()
                report.update(
                    status="READY"
                    if self.engine.complete_day(key, day, site["timezone"])
                    else "INCOMPLETE",
                    last_success=source["verified_at"],
                    reason=None,
                    changed=changed,
                )
                if site.get("nordpool_entry") and self.official.last_errors:
                    report.update(
                        status="STALE",
                        reason="Nord Pool refresh failed; retained verified intervals",
                    )
                return changed
            except (
                ValueError,
                TypeError,
                KeyError,
                OSError,
                HomeAssistantError,
                TimeoutError,
            ) as err:
                report.update(reason=str(err), changed=False)
                return False  # Keep the last durable verified prices, never invent zeros.
