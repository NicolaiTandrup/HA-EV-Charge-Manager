"""Civil-time publication refresh, conditional retries and restart recovery."""

from datetime import timedelta
from zoneinfo import ZoneInfo

from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .price_engine import day_bounds

TIMES = ((0, 1), (13, 5), (13, 20), (13, 40), (23, 59))
ZONE = ZoneInfo("Europe/Copenhagen")


class PriceSchedule:
    def __init__(self, coordinator):
        self.coordinator = coordinator
        self.hass = coordinator.hass
        self.store = Store(
            self.hass, 1, f"ev_charge_manager.{coordinator.entry.entry_id}.price_schedule"
        )
        self.days = {}
        self.cancel = None
        self.active = False

    def complete(self, site, day):
        key = site["id"]
        return (
            self.coordinator.price_engine.complete_day(key, day, site["timezone"])
            and self.days.get(key, {}).get(str(day), {}).get("status") == "READY"
        )

    async def refresh_day(self, site, day, now):
        key = site["id"]
        changed = await self.coordinator.price_updater.refresh(site, now, force=True, dates=[day])
        start, end = day_bounds(day, site["timezone"])
        rows = self.coordinator.price_engine.lookup(key, start, end)
        report = self.coordinator.price_updater.status[key]
        complete = self.coordinator.price_engine.complete_day(key, day, site["timezone"])
        state = (
            "READY"
            if complete and report["status"] not in {"ERROR", "STALE"}
            else report["status"]
            if report["status"] in {"ERROR", "STALE"}
            else "INCOMPLETE"
        )
        self.days.setdefault(key, {})[str(day)] = {
            "status": state,
            "requested_date": str(day),
            "last_attempt": now.isoformat(),
            "last_success": report.get("last_success"),
            "valid_slots": len(rows),
            "expected_slots": int((end - start).total_seconds() / 900),
            "reason": report.get("reason"),
        }
        # Keep a bounded operational log; price history has independent retention.
        self.days[key] = {
            d: r for d, r in self.days[key].items() if d >= str(day - timedelta(days=7))
        }
        await self.store.async_save(self.days)
        return changed

    async def startup(self):
        self.days = await self.store.async_load() or {}
        now = dt_util.utcnow()
        for optimizer in self.coordinator.sites.values():
            site = optimizer.site
            today = now.astimezone(ZONE).date()
            # Always verify current day; also reconcile known/missing next day.
            for day in (today, today + timedelta(days=1)):
                await self.refresh_day(site, day, now)

    async def run(self, now, hour, minute):
        changed = False
        today = now.astimezone(ZONE).date()
        for optimizer in self.coordinator.sites.values():
            site = optimizer.site
            day = today if (hour, minute) == (0, 1) else today + timedelta(days=1)
            unconditional = (hour, minute) in {(0, 1), (13, 5)}
            if unconditional or not self.complete(site, day):
                changed = await self.refresh_day(site, day, now) or changed
        if changed:
            await self.coordinator.async_request_refresh()
        return changed

    def listen(self):
        self.active = True
        self._arm()
        self.coordinator.entry.async_on_unload(self.stop)

    def stop(self):
        self.active = False
        if self.cancel:
            self.cancel()
            self.cancel = None

    def _arm(self):
        now = dt_util.utcnow()
        local = now.astimezone(ZONE)
        choices = []
        for offset in (0, 1):
            for hour, minute in TIMES:
                candidate = (local + timedelta(days=offset)).replace(
                    hour=hour, minute=minute, second=0, microsecond=0
                )
                if candidate > local:
                    choices.append(candidate)
        target = min(choices)

        async def fire(_):
            try:
                await self.run(dt_util.utcnow(), target.hour, target.minute)
            finally:
                if self.active:
                    self._arm()

        self.cancel = async_track_point_in_utc_time(self.hass, fire, target)
