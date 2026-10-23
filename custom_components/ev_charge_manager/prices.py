"""Official Nord Pool read service plus explicit all-in tariff composition."""

from dataclasses import replace
from datetime import timedelta
from math import isfinite
from zoneinfo import ZoneInfo

from homeassistant.exceptions import HomeAssistantError

from .adapters import parse_prices


def all_in(slots, tariff):
    """Tariff components are DKK/kWh ex VAT; pre-inclusive mode forbids additions."""
    mode = tariff.get("mode", "all_in")
    parts = [float(tariff.get(k, 0)) for k in ("grid", "tax", "supplier")]
    vat = float(tariff.get("vat", 0))
    if not all(isfinite(v) and v >= 0 for v in [*parts, vat]):
        raise ValueError("Invalid tariff")
    if mode == "all_in":
        if any([*parts, vat]) or tariff.get("grid_slots"):
            raise ValueError("All-in source cannot have duplicate tariff additions")
        return slots
    if mode not in {"spot_ex_vat", "spot_incl_vat"}:
        raise ValueError("Explicit price basis required")
    result = []
    for slot in slots:
        grid = 0.0
        if "grid_slots" in tariff:
            covering = [
                g for g in tariff["grid_slots"] if g.start <= slot.start and g.end >= slot.end
            ]
            if len(covering) != 1:
                raise ValueError("Grid tariff does not cover every price interval")
            grid = covering[0].price
            if grid < 0:
                raise ValueError("Negative grid tariff")
        result.append(
            replace(
                slot,
                price=(slot.price / (1 + vat) if mode == "spot_incl_vat" else slot.price)
                * (1 + vat)
                + (sum(parts) + grid) * (1 + vat),
            )
        )
    return result


class OfficialPrices:
    def __init__(self, hass):
        self.hass, self.cache = hass, {}
        self.attempts = {}

    async def get(self, site, now, *, compose=True, force=False, dates=None):
        rows = []
        self.last_errors = []
        today = now.astimezone(ZoneInfo(site["timezone"])).date()
        for day in dates or (today, today + timedelta(days=1)):
            key = (site["nordpool_entry"], site.get("area", "DK2"), str(day))
            cached = self.cache.get(key)
            attempted = self.attempts.get(key)
            if (force or cached is None or (now - cached[0]).total_seconds() >= 3600) and (
                force or attempted is None or (now - attempted).total_seconds() >= 900
            ):
                self.attempts[key] = now
                try:
                    response = await self.hass.services.async_call(
                        "nordpool",
                        "get_prices_for_date",
                        {
                            "config_entry": key[0],
                            "date": key[2],
                            "areas": [key[1]],
                            "currency": "DKK",
                        },
                        blocking=True,
                        return_response=True,
                    )
                    data = response[key[1]]
                    parse_prices({"slots": data}, multiplier=0.001)
                    self.cache[key] = (now, data)
                except HomeAssistantError, ValueError, KeyError, TypeError, TimeoutError:
                    self.last_errors.append(str(day))
                    # Cached values expire rather than hiding a broken price source.
                    if cached is None or (now - cached[0]).total_seconds() >= 7200:
                        continue
            cached = self.cache.get(key)
            if cached and (now - cached[0]).total_seconds() < 7200:
                rows.extend(cached[1])
        self.cache = {k: v for k, v in self.cache.items() if (now - v[0]).total_seconds() < 172800}
        self.attempts = {
            k: v for k, v in self.attempts.items() if (now - v).total_seconds() < 172800
        }
        slots = parse_prices({"slots": rows}, multiplier=0.001)
        return all_in(slots, site["tariff"]) if compose else slots
