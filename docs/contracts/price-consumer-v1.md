# Price lookup contract v1 — producer/consumer proposal

Status: draft interoperability proposal, 2026-10-24. Authoritative producer:
NicolaiTandrup/HA-Energy-Price-Engine, domain `ha_energy_price_engine`.
Consumer: `ev_charge_manager`. The producer repository currently has no runtime
implementation. Consumer tests use mocked services, not a deployed producer.
Review changes together in the separate repository PRs; no cutover is implied.

## Read-only range service

`ha_energy_price_engine.get_prices` supports response-only HA service calls:

```json
{"api_version":1,"config_entry_id":"producer-entry","site_id":"producer-site","start":"2026-10-24T12:00:00+00:00","end":"2026-10-24T12:15:00+00:00"}
```

Start/end are inclusive/exclusive UTC quarter boundaries. Maximum 1000 intervals.
The explicit producer config entry and site identify the table; display names,
entity suffixes and household/supplier names never establish identity.

Response example (synthetic, no private household data):

```json
{
  "api_version": 1,
  "producer_entry_id": "producer-entry",
  "site_id": "producer-site",
  "currency": "DKK",
  "unit": "DKK/kWh",
  "vat_included": true,
  "revision": 1,
  "status": "READY",
  "verified_at": "2026-10-24T12:00:00+00:00",
  "slots": [{"start":"2026-10-24T12:00:00+00:00","end":"2026-10-24T12:15:00+00:00","final_price_incl_vat":1.25}]
}
```

`api_version` and `revision` are actual integers, not booleans. Revision is durable,
nonnegative and monotonic per producer/site. Currency/unit/VAT inclusion are explicit;
no consumer FX, unit scaling, VAT multiplication or tariff reconstruction. Prices
may be negative or genuinely zero; missing/null/nonfinite prices are never zero.
Unknown fields may be ignored compatibly; breaking semantics require a new version.

Producer returns precomputed durable final prices. Reads must never fetch sources,
recalculate charges, or mutate price history. Settled historical amounts remain
immutable; future corrections advance the revision. Component/invoice details stay
producer-owned and need not cross this narrow consumer API.

## Availability and freshness

- READY: sorted, unique, contiguous quarters cover the exact requested range.
- INCOMPLETE: only verified available quarters are returned, possibly with gaps.
  EV may produce a conditional/provisional plan using known intervals, never filling
  gaps or gambling on missing prices. A complete plan may use a sufficient subset.
- STALE / ERROR: no new EV schedule is trusted. No stale cache is silently promoted
  to READY. Producer unload/missing service fails closed even within lookup throttle.

`verified_at` is the actual latest relevant successful verification, not read time.
It must be offset-aware, not future-dated. Consumer default maximum age is 36 hours,
UI-configurable up to 48 hours for current/future planning. Producer policies can be
stricter and report STALE sooner. Range results may include older settled historical
rows; a future dedicated accounting backfill API must define their age semantics.
Consumer currently queries the recent measurement window through next local day.

## Revision event

Event `ha_energy_price_engine_prices_updated`:

```json
{"api_version":1,"producer_entry_id":"producer-entry","site_id":"producer-site","revision":2,"affected_start":"2026-10-24T13:00:00+00:00","affected_end":"2026-10-24T23:00:00+00:00"}
```

Emit only for actual changed future final prices, not unchanged source checks,
metadata-only updates or dashboard reads. Consumer filters entry/site/version and
coalesces duplicate/past revision numbers. It requests a new range after a matching
revision; it never reaches into producer private runtime objects.

Consumer normally checks the read-only lookup no more than once per minute, with
bounded retry when not loaded. Matching revision events can bypass that interval.
Slot expiry/freshness and entry readiness are checked locally on every use. A failed
response clears usable schedule data; last known revision still guards rollback.
Producer should expose its own availability diagnostics; no mandatory dashboard or
supplier/vehicle integration dependency is introduced.

## Scheduling and rollout

EV retains staged SoC priorities, long-trip safety margin, Cheap Boost simulation,
0.005 DKK/kWh tie groups with earliest-first, guest exclusion, shared-site limits,
30-minute regular replanning and earlier meaningful-input/deadline invalidation.
No missing-price fallback issues a real start/stop command. No vehicle/charger
transport exists in the preview.

New EV sites select the independent producer. Existing pricing settings and tested
code remain explicitly labeled migration/reference; no automatic entry migration,
rate copy, Node-RED edits or production source switch occurs. Producer API readiness
and independent runtime tests are required before claiming real interoperability.
