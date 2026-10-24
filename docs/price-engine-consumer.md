# Standalone Price Engine consumer preview

Producer implementation and public API: NicolaiTandrup/HA-Energy-Price-Engine PR #7.
This separate draft is based on EV Manager PR #12, retaining that unmerged stack.

Per site, explicitly select `price_engine_site` in native options, without a legacy
price entity or Nord Pool entry. No site is migrated automatically. In this mode
all retrieval, tariff sources, VAT arithmetic, persistence and price publishing
belong to `ha_energy_price_engine`; legacy tariff form fields are not applied.
The adapter only copies API v1's final VAT-inclusive DKK/kWh values into PriceSlot.

Discovery backs off (30 seconds up to 15 minutes). Missing/unloaded/stale/error/
incomplete prices disable valid plans, never substitute zero or legacy arithmetic.
The range covers the current quarter through the end of next local day: before
complete next-day publication this conservative preview defers new plans. Narrower
per-vehicle deadline range selection is a possible follow-up, not a hidden fallback.
Future price-revision events refresh matching sites; the existing regular 30-minute
optimizer cadence and earliest-slot tie-break are preserved. Sources are never
queried by this consumer. A different site/revision/unit/coverage is rejected.

Existing configurations remain legacy simulations until explicitly migrated and
reviewed; this preserves the working PR #11/#12 stack without claiming two owners
for an externally configured site. No production Node-RED, HA, charging controls,
merge, stable release or cutover is changed/authorized by these code changes.

Tests mock producer responses and run the actual EV Manager HA lifecycle. The
producer separately retains upstream golden fixtures for all 92/96/100-slot DST
and seasonal cases. Owner-exported read-only broker inputs/outputs are still needed
for actual household/summer-house parity; no real rates for unknown periods are
inferred. See docs/DEVELOPMENT_STATUS.md for exact results and continuation.

## Cross-repository contract tests

CI checks out producer checkpoint `f362507` in `price-engine-reference` and runs the
real API/Store contract on 92/96/100-slot days, site isolation and stale handling.
Locally use `PRICE_ENGINE_SOURCE=/path/to/HA-Energy-Price-Engine python -m pytest`.
Use that pinned checkpoint for reproducibility; keep any reference checkout outside
tracked files. Tests fail clearly rather than skip when the reference is missing.
