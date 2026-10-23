"""Verified Datahub tariff identity, local-hour normalization and durable cache."""

import json
from asyncio import Lock
from datetime import datetime, timedelta
from hashlib import sha256
from math import isfinite
from zoneinfo import ZoneInfo

from aiohttp import ClientTimeout
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

from .planner import PriceSlot
from .price_engine import day_bounds

RADIUS_GLN = "5790000705689"
RADIUS_CODE = "DT_C_01"
URL = "https://api.energidataservice.dk/dataset/DatahubPricelist"
ZONE = ZoneInfo("Europe/Copenhagen")


def normalize_tariffs(records, gln, code, start, end):
    """Explicit GLN/product/D03/PT1H only. Prices are verified DKK/kWh ex VAT.

    VATClass is indicative according to dataset metadata and is NOT used to infer
    inclusion. The Radius preset's exclusion convention was verified against the
    official application's raw-price * 1.25 * 100 inclusive display calculation.
    """
    validated = []
    for row in records:
        if (
            row.get("GLN_Number") != gln
            or row.get("ChargeTypeCode") != code
            or row.get("ChargeType") != "D03"
            or row.get("ResolutionDuration") != "PT1H"
        ):
            raise ValueError("Unrecognized tariff owner/product/resolution")
        raw_from = datetime.fromisoformat(row["ValidFrom"])
        if raw_from.tzinfo is not None:
            raise ValueError("Expected documented local-naive Datahub effective date")
        a = raw_from.replace(tzinfo=ZONE)
        b = (
            datetime.fromisoformat(row["ValidTo"]).replace(tzinfo=ZONE)
            if row.get("ValidTo")
            else None
        )
        values = [float(row[f"Price{i}"]) for i in range(1, 25)]
        if any(not isfinite(v) or v < 0 for v in values) or (b and b <= a):
            raise ValueError("Invalid effective tariff range/amount")
        validated.append((a, b, values, row))
    slots = []
    used = {}
    cursor = start
    while cursor < end:
        local = cursor.astimezone(ZONE)
        options = [r for r in validated if r[0] <= local and (r[1] is None or local < r[1])]
        if len(options) != 1:
            raise ValueError("Missing or overlapping effective tariff versions")
        a, b, values, row = options[0]
        day_start, day_end = day_bounds(local.date())
        hour = local.hour
        if hour == 2 and day_end - day_start != timedelta(days=1):
            hour = 1  # Dataset's documented preceding-hour rule on DST affected hour.
        slots.append(PriceSlot(cursor, cursor + timedelta(minutes=15), values[hour]))
        used[a.isoformat()] = {
            "from": a.isoformat(),
            "to": b.isoformat() if b else None,
            "prices": values,
        }
        cursor += timedelta(minutes=15)
    version = sha256(json.dumps(used, sort_keys=True).encode()).hexdigest()
    return slots, {
        "provider": "DatahubPricelist",
        "gln": gln,
        "product": code,
        "charge_type": "D03",
        "unit": "DKK/kWh",
        "vat_included": False,
        "version": version,
        "effective_versions": list(used),
        "effective_ranges": [{"from": v["from"], "to": v["to"]} for v in used.values()],
        "url": URL,
    }


class TariffSource:
    def __init__(self, hass, entry_id):
        self.hass = hass
        self.store = Store(hass, 1, f"ev_charge_manager.{entry_id}.tariffs")
        self.cache = {}
        self.lock = Lock()

    async def load(self):
        saved = await self.store.async_load()
        self.cache = saved if isinstance(saved, dict) else {}

    async def get(self, site, start, end, now):
        gln = site.get("dso_gln", RADIUS_GLN)
        code = site.get("dso_product", RADIUS_CODE)
        if site.get("dso_mode") == "radius_c":
            gln, code = RADIUS_GLN, RADIUS_CODE
        key = gln + ":" + code
        async with self.lock:
            cache = self.cache.get(key, {})
            fetched = (
                datetime.fromisoformat(cache["fetched_at"]) if cache.get("fetched_at") else None
            )
            attempted = (
                datetime.fromisoformat(cache["attempted_at"]) if cache.get("attempted_at") else None
            )
            stale = not fetched or fetched.astimezone(ZONE).date() != now.astimezone(ZONE).date()
            warning = None
            if stale and (attempted is None or (now - attempted).total_seconds() >= 3600):
                cache["attempted_at"] = now.isoformat()
                try:
                    async with async_get_clientsession(self.hass).get(
                        URL,
                        params={
                            "filter": json.dumps(
                                {"GLN_Number": gln, "ChargeType": "D03", "ChargeTypeCode": code}
                            ),
                            "limit": 1000,
                        },
                        timeout=ClientTimeout(total=20),
                    ) as response:
                        response.raise_for_status()
                        payload = await response.json()
                    records = payload["records"]
                    if not isinstance(records, list) or not records or len(records) >= 1000:
                        raise ValueError("Missing/truncated tariff dataset")
                    normalize_tariffs(records, gln, code, start, end)
                    cache.update(records=records, fetched_at=now.isoformat())
                    self.cache[key] = cache
                    await self.store.async_save(self.cache)
                    fetched = now
                    stale = False
                except ValueError, TypeError, KeyError, TimeoutError, OSError, __import__(
                    "aiohttp"
                ).ClientError:
                    warning = "Tariff fetch failed; using last verified schedule if valid"
                    self.cache[key] = cache
                    await self.store.async_save(self.cache)
            if (
                not fetched
                or (now - fetched).total_seconds() > site.get("dso_stale_days", 7) * 86400
            ):
                raise ValueError("No sufficiently recent verified tariff cache")
            slots, metadata = normalize_tariffs(cache.get("records", []), gln, code, start, end)
            metadata.update(
                fetched_at=fetched.isoformat(),
                warning=warning or ("Tariff cache stale" if stale else None),
            )
            return slots, metadata
