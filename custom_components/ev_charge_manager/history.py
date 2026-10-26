"""Measured history, independent of plans. No extrapolation across downtime."""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from math import isfinite
from zoneinfo import ZoneInfo

from .planner import PriceSlot, utc


@dataclass
class History:
    energy_kwh: float = 0
    cost: float = 0
    distance_km: float = 0
    unpriced_energy_kwh: float = 0
    daily: dict = field(default_factory=dict)
    calendar_timezone: str = "UTC"
    odometer_source: str | None = None
    last_odometer_km: float | None = None
    # Samples are deliberately not persisted; restart establishes a fresh baseline.
    sampled_at: datetime | None = None
    last_power_kw: float = 0
    was_eligible: bool = False

    def __post_init__(self):
        ZoneInfo(self.calendar_timezone)
        if not isinstance(self.daily, dict):
            raise ValueError("Invalid calendar records")
        for day, values in self.daily.items():
            date.fromisoformat(day)
            if not isinstance(values, dict) or any(
                key not in {"energy_kwh", "cost", "unpriced_energy_kwh", "distance_km"}
                or not isinstance(value, (int, float))
                or not isfinite(value)
                or (key != "cost" and value < 0)
                for key, value in values.items()
            ):
                raise ValueError("Invalid calendar measurements")
        if any(
            not isfinite(v) or v < 0
            for v in (self.energy_kwh, self.distance_km, self.unpriced_energy_kwh)
        ) or not isfinite(self.cost):
            raise ValueError("Invalid persisted measured totals")
        if self.unpriced_energy_kwh > self.energy_kwh + 1e-9 or (
            self.last_odometer_km is not None
            and (not isfinite(self.last_odometer_km) or self.last_odometer_km < 0)
        ):
            raise ValueError("Invalid persisted history coverage/odometer")

    def sample_power(
        self,
        now: datetime,
        power_kw: float,
        eligible: bool,
        slots: list[PriceSlot],
        *,
        timezone=None,
    ):
        now = utc(now)
        if timezone and not self.daily:
            ZoneInfo(timezone)
            self.calendar_timezone = timezone
        eligible = eligible and isfinite(power_kw) and power_kw >= 0
        previous = self.sampled_at
        elapsed = (now - previous).total_seconds() if previous else 0
        if previous and self.was_eligible and eligible and 0 < elapsed <= 180:
            measured = (self.last_power_kw + power_kw) / 2 * elapsed / 3600
            self.energy_kwh += measured
            segments = []
            cursor = previous
            for slot in slots:
                start, end = max(previous, slot.start), min(now, slot.end)
                if end <= start:
                    continue
                if start != cursor:
                    break
                # Linear interpolation across the sample, split at price boundaries.
                p0 = (
                    self.last_power_kw
                    + (power_kw - self.last_power_kw) * (start - previous).total_seconds() / elapsed
                )
                p1 = (
                    self.last_power_kw
                    + (power_kw - self.last_power_kw) * (end - previous).total_seconds() / elapsed
                )
                energy = (p0 + p1) / 2 * (end - start).total_seconds() / 3600
                segments.append((energy, energy * slot.price))
                cursor = end
            if cursor == now:
                self.cost += sum(c for _, c in segments)
            else:
                self.unpriced_energy_kwh += measured
            self._record_power(previous, now, power_kw, slots, cursor == now)
        self.sampled_at, self.last_power_kw, self.was_eligible = (
            now,
            power_kw if isfinite(power_kw) and power_kw >= 0 else 0,
            eligible,
        )

    def sample_odometer(self, source: str, value: float, unit: str, *, now=None, timezone=None):
        if unit not in ("km", "mi") or not isfinite(value) or value < 0:
            return
        current = value * (1.609344 if unit == "mi" else 1)
        previous = self.last_odometer_km
        if self.odometer_source != source or previous is None or current < previous:
            self.odometer_source, self.last_odometer_km = source, current
            return
        delta = current - previous
        if delta <= 5000:
            self.distance_km += delta
            if now is not None and delta:
                if timezone and not self.daily:
                    ZoneInfo(timezone)
                    self.calendar_timezone = timezone
                self._record_day(
                    utc(now).astimezone(ZoneInfo(self.calendar_timezone)).date(), distance_km=delta
                )
            self.last_odometer_km = current

    def _record_day(self, day, **amounts):
        record = self.daily.setdefault(str(day), {})
        for key, amount in amounts.items():
            record[key] = record.get(key, 0) + amount

    def _record_power(self, previous, now, power_kw, slots, priced):
        zone = ZoneInfo(self.calendar_timezone)
        elapsed = (now - previous).total_seconds()
        points = {previous, now}
        local = previous.astimezone(zone)
        midnight = utc(
            (local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        )
        if previous < midnight < now:
            points.add(midnight)
        for slot in slots:
            points.update(t for t in (slot.start, slot.end) if previous < t < now)
        points = sorted(points)
        for start, end in zip(points, points[1:]):
            p0 = (
                self.last_power_kw
                + (power_kw - self.last_power_kw) * (start - previous).total_seconds() / elapsed
            )
            p1 = (
                self.last_power_kw
                + (power_kw - self.last_power_kw) * (end - previous).total_seconds() / elapsed
            )
            energy = (p0 + p1) / 2 * (end - start).total_seconds() / 3600
            price = (
                next((s.price for s in slots if s.start <= start and end <= s.end), 0)
                if priced
                else 0
            )
            self._record_day(
                start.astimezone(zone).date(),
                energy_kwh=energy,
                cost=energy * price,
                unpriced_energy_kwh=0 if priced else energy,
            )

    def period_start(self, period, now):
        local = (
            utc(now)
            .astimezone(ZoneInfo(self.calendar_timezone))
            .replace(hour=0, minute=0, second=0, microsecond=0)
        )
        if period == "week":
            return local - timedelta(days=local.weekday())
        if period == "month":
            return local.replace(day=1)
        if period == "year":
            return local.replace(month=1, day=1)
        if period != "day":
            raise ValueError("Unknown calendar period")
        return local

    def period_total(self, kind, period, now):
        first = str(self.period_start(period, now).date())
        last = str(utc(now).astimezone(ZoneInfo(self.calendar_timezone)).date())
        return sum(
            record.get(kind, 0) for day, record in self.daily.items() if first <= day <= last
        )

    def persistent(self):
        return {
            name: getattr(self, name)
            for name in (
                "daily",
                "calendar_timezone",
                "energy_kwh",
                "cost",
                "distance_km",
                "unpriced_energy_kwh",
                "odometer_source",
                "last_odometer_km",
            )
        }
