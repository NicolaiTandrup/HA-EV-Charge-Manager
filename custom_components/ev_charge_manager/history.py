"""Measured history, independent of plans. No extrapolation across downtime."""

from dataclasses import dataclass
from datetime import datetime
from math import isfinite

from .planner import PriceSlot, utc


@dataclass
class History:
    energy_kwh: float = 0
    cost: float = 0
    distance_km: float = 0
    unpriced_energy_kwh: float = 0
    odometer_source: str | None = None
    last_odometer_km: float | None = None
    # Samples are deliberately not persisted; restart establishes a fresh baseline.
    sampled_at: datetime | None = None
    last_power_kw: float = 0
    was_eligible: bool = False

    def __post_init__(self):
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

    def sample_power(self, now: datetime, power_kw: float, eligible: bool, slots: list[PriceSlot]):
        now = utc(now)
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
        self.sampled_at, self.last_power_kw, self.was_eligible = (
            now,
            power_kw if isfinite(power_kw) and power_kw >= 0 else 0,
            eligible,
        )

    def sample_odometer(self, source: str, value: float, unit: str):
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
            self.last_odometer_km = current

    def persistent(self):
        return {
            name: getattr(self, name)
            for name in (
                "energy_kwh",
                "cost",
                "distance_km",
                "unpriced_energy_kwh",
                "odometer_source",
                "last_odometer_km",
            )
        }
