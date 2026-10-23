# Development handoff

Updated 2026-10-23. Canonical continuation file; read AGENTS.md first.

## Git / PR stack

- Owner restart point: `4051ec0` on `feat/unified-read-only-integration` (PR #6).
- PR #5: architecture baseline `feat/unified-architecture`, unchanged/unmerged.
- PR #6: `feat/unified-read-only-integration`, now `f488748` (Issue #2 rename and
  provider-management work). Remote push/PR tests, hassfest and HACS all passed.
- PR #11: `feat/persistent-price-engine`, head `5c32dc9`, based on PR #6. Persistent
  Price Engine (#9) and scheduled refresh (#10). Remote push/PR tests, hassfest and
  HACS all passed at `d1c66b7` and `5c32dc9`.
- Active: `feat/verified-danish-pricing`, based on PR #11. Initial source/component
  checkpoint `b9ce79a` passed remote push tests/hassfest/HACS. Hardening checkpoint `afe2e88` passed local **137 tests, zero skips**, Ruff/format,
  official hassfest and all remote push/PR tests, hassfest and HACS.
- Current checkpoint `Align tariff cache with morning publication verification`:
  **138 passed, zero skips; 91% coverage**, Ruff/format and official local hassfest
  passed. It prevents midnight cache reads consuming the afternoon verification
  of morning source updates. Check its exact remote CI head after pushing.
- Source/component draft PR #12 is open from the active branch to
  `feat/persistent-price-engine`. Stack: #5 → #6 → #11 → #12. All remain drafts;
  do not merge the stack.

## Completed (do not repeat)

- Original port/architecture/snapshot safety and permanent handoff workflow.
- Issue #2 rename: four regression failures reproduced first. Stable registry IDs
  persist through live/offline rename; every field read verifies registry identity,
  expected device ownership, enabled state and unique logical owner. Deleted IDs
  never rebind by old entity name. Internal reconciliations do not reset sessions.
  Invalid/unregistered legacy mappings require explicit reviewed remapping.
- Issue #2 UI: promote/reorder/remove providers and replace devices via reviewed
  mappings without changing logical vehicle UUID/provider ID; edits retain order.
- #9: atomic per-site HA Store tables, immutable records and indexed lookup-only
  consumers, 365-day history retention, future-only verified corrections,
  unchanged-update signatures, source/component/VAT conventions. Store/restart,
  failed writes, concurrency, history and 92/96/100-slot DST tests pass.
- #10: Copenhagen 13:05 publication; conditional 13:20/13:40 retries and 23:59
  rescue; unconditional 00:01 current-day sync. Startup verifies current/next day.
  Partial corrected publications never mix with an old complete table and become
  READY. Separate persisted operational metadata records requested date, actual
  source/stored/expected counts, last success/attempt, reason and status.
- Pricing reads never fetch or compose. A changed price requests one refresh;
  unchanged watchdogs reuse plans until a 30-minute regular tick or relevant input,
  price, allocation boundary or deadline change. History/freshness remains separate.
- #7 actual Radius C availability verified from public API and metadata; official
  Radius app confirms ex-VAT display conversion. GLN 5790000705689, D03/DT_C_01,
  PT1H. Actual rows retained as fixtures. Native optional daily cached adapter,
  local-hour/effective/DST rules, outage backoff, stale warnings, explicit manual
  fallback. No fuzzy product match or VATClass inference. Diagnostics expose
  current DSO amount, next change, provenance and daily verification counts.
- #8: dated/verified component schema, per-component VAT/unit normalization,
  effective periods, locked overrides, explicit registered-heating/usage policy,
  subscription separation. Optional public policy uses only Issue #8's documented
  2026 network/system and 2026–2027 tax periods. Unknown future rates fail closed.
  No inferred EWII supplier contract.

## Current blocker / owner decision

An asynchronous question is pending for actual **per-site EWII markup and VAT
inclusion**. Need its effective period/source reference as well. Neither legacy
3.75 øre nor advertised 6.5 øre is assumed. Advanced dated all-in pricing requires
an explicit supplier rule; tests use a clearly labeled fictional test contract.
Owner household parity also needs read-only Energy Price Broker output/input
exports. No live HA access or household commands were attempted.

Once supplied: enter equivalent non-secret test fixtures (no credentials/customer
identifiers), validate each site's expected all-in breakdown against the broker,
and extend the dated source rules only for verified periods. Do not apply rates to
running HA or Node-RED. Keep #7/#8 open until contract/source parity is verified.

## Remaining priorities

1. Confirm latest publication-cache checkpoint CI, then resolve owner input below.
2. Resolve owner EWII terms/read-only comparison fixtures; no rate speculation.
3. Extend authoritative dated national rates only when published/verified. Current
   adapter is a bounded policy schedule, not a live legislative discovery service.
4. Broader provider/DSO presets require verified identity/capability/VAT metadata.
   Pricing/charger-status entity references remain strings; vehicle references are
   registry-pinned. Hardware observation needs separate owner authorization.
5. Historical exports/ledger beyond 365 days, energy/cost/distance entities, richer
   site/currency configuration and wider parity scenarios remain follow-ups.

## Commands / validation

From `/workspace/HA-EV-Charge-Manager`, existing Python 3.14.8 environment:

```sh
git status --short --branch
git log -6 --oneline
/workspace/ev-manager-venv/bin/python -m pytest --cov=custom_components.ev_charge_manager --cov-report=term
/workspace/ev-manager-venv/bin/python -m pytest tests/test_registry.py tests/test_provider_management.py tests/test_price_engine.py tests/test_price_schedule.py tests/test_tariff_source.py tests/test_price_components.py
/workspace/ev-manager-venv/bin/ruff check custom_components tests
/workspace/ev-manager-venv/bin/ruff format --check custom_components tests
docker run --rm -v /workspace/HA-EV-Charge-Manager:/github/workspace ghcr.io/home-assistant/hassfest
gh pr checks 6 --repo NicolaiTandrup/HA-EV-Charge-Manager
gh pr checks 11 --repo NicolaiTandrup/HA-EV-Charge-Manager
git diff --check
```

Node.js 24 is required for five original Node-RED JavaScript parity cases; zero
skips in the last full run. Do not reinstall working dependencies. Local full HACS
container DNS is unavailable; use real remote HACS validation, not bypasses.

## Safety / continuation

No Node-RED changes, live HA/vehicle/charger commands, merge, stable release or
production cutover. Public tariff HTTP reads are opt-in; manifest cloud_polling
reflects that optional feature. Default/manual mode makes none. No secrets or
production configuration are committed. Future real commissioning is per vehicle
AND charger. Guest downtime reconciliation and no live executor boundaries remain.

At checkpoints update actual results, commit/push coherent changes and comment on
active PR/issue. A handoff cannot contain its own hash; use checkpoint subject and
exact prior validated hashes. Reconstruct interruptions from Git/PR/tests before
repeating work. Resume owner-contract validation when inputs arrive; do not rebuild
the completed registry, persistent engine, scheduling or verified Radius adapter.
