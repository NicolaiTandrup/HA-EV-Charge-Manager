# Producer-owned read-only price API v1

Authoritative implementation and contract:
[Price Engine draft #7](https://github.com/NicolaiTandrup/HA-Energy-Price-Engine/pull/7),
`docs/API.md` and `custom_components/ha_energy_price_engine/api.py`.
EV reconciliation reuses the adapter/test approach in
[companion draft #15](https://github.com/NicolaiTandrup/HA-EV-Charge-Manager/pull/15).
The prior `get_prices` service proposal in EV #13 / producer #6 is superseded;
no such service is required or called.

Discover lazily with `get_api(hass, version=1)` from the public module. `sites()`
returns immutable site descriptors. `lookup(site_id, start, end, now=now)` reads
precomputed persisted prices without source fetching, arithmetic or writes.
Ranges are aware UTC, quarter-aligned, half-open `[start,end)`; local DST days can
contain 92, 96 or 100 quarters. Missing discovery/site is not free electricity.

Frozen `PriceResult` carries api_version, site_id, status, records, expected_slots,
valid_slots, last_success, reason and current revision. Each frozen record includes
site_id, start/end, final_price_incl_vat, currency DKK, unit DKK/kWh, source/component
JSON, calculated_at and its own revision. Older settled rows may have older revisions.
Negative and explicit zero prices pass through unchanged. No VAT is added by EV.

EV accepts only READY with exact contiguous range coverage. INCOMPLETE, STALE,
ERROR and NOT_LOADED yield no usable scheduling prices; no legacy fallback occurs.
Producer controls operational readiness, including current/future date verification.
EV additionally checks configured maximum verification age, nonfinite values,
units, identity and monotonic site revisions. The selected loaded config entry's
public durable `id` must match the selected global producer site ID; EV does not
inspect private runtime coordinator objects. No automatic entry conversion occurs.

The synthetic `example-response-v1.json` is retained only as an **internal normalized
validator fixture**, not a serialized producer API/service response. API tests also
exercise actual producer objects. Historical accounting backfill needs a separate
consumer path that respects the producer's settled historical readiness semantics.

Subscribe to `ha_energy_price_engine_price_revision_v1`: api_version, site_id,
revision, start/end and affected_slots. Events follow durable future-price changes;
metadata-only checks do not emit. Filter version/site, coalesce duplicate revisions,
and re-read; event data alone is never usable price data. Periodic read retries are
bounded to once/minute and loaded-entry checks apply on every use.

Charging priorities, 30-minute regular replanning, 0.005 DKK/kWh earliest-slot tie
policy, guest exclusion, safe simulations and shared-site limits remain unchanged.
No commands, live HA access, production cutover, release or merge are authorized.

## Reproducible cross-repository validation

CI checks out producer `46b33bf50773082b6d942816c676dd098ee6bad1` into
`price-engine-reference`. Locally, set `PRICE_ENGINE_SOURCE` to an isolated export
of that commit, then run:

```sh
PRICE_ENGINE_SOURCE=/tmp/ev-price-producer-reference /workspace/ev-manager-venv/bin/python -m pytest tests/test_price_api_interop.py tests/test_price_consumer.py
```

These are real producer API/ledger calls using synthetic inputs and temporary HA
storage, not live hardware/source acceptance. Do not claim invoice verification.
