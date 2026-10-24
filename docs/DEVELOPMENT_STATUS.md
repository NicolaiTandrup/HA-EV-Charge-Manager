# Development handoff

Updated 2026-10-23. Canonical continuation file; read AGENTS.md first.

## Active standalone consumer checkpoint (2026-10-24)

Branch: `feat/price-engine-consumer`, based on PR #12 head
`9d949c6d0905646d1bbf973ea2edb47846e1607d`. This is a separate draft stack
extension; no existing PR #11/#12 branch is changed or merged.
Checkpoint subject: `feat: consume standalone Price Engine API v1 without local pricing`.
Producer: NicolaiTandrup/HA-Energy-Price-Engine draft PR #7.

Completed: immutable API v1 final-price adapter; explicit native per-site
`price_engine_site` selection exclusive of legacy price entity/Nord Pool source;
producer-only retrieval/calculation/storage/publishing; skip local source schedules
and price sensors for external sites; future revision event subscription; bounded
discovery backoff; fail-closed invalid/missing/stale/unloaded/cross-site/incorrect-unit
responses. Existing 30-minute optimizer cadence and earliest-slot tie-break untouched.
No existing site migrates automatically. Other legacy simulation sites retain their
reviewed PR #11/#12 code until separately migrated.

Local validation with locked producer `.venv` Python 3.14.8 and Node 24:
`PRICE_ENGINE_SOURCE=/workspace/HA-Energy-Price-Engine python -m pytest
--cov=custom_components.ev_charge_manager`: **153 passed, zero skips, 91% coverage**.
Ruff check and format pass. The focused consumer module has 98% coverage.
Cross-repository tests exercise the real producer API/HA Store on 92/96/100-slot
DST days, site isolation and stale handling. CI checks out producer exact commit
`f36250715eb3ec2e8a47424a780943192c96a634`; local producer has further equivalent
hardening. Native HA lifecycle tests prove no consumer fetch/calculation and stale
prices invalidate forecasts rather than retaining a valid cached plan.

Remaining: push this milestone, open draft to `feat/verified-danish-pricing`, verify
exact-head remote tests/hassfest/HACS; record actual outcomes here. Official local
hassfest result must be recorded after it completes. No remote CI claimed yet.
Read-only owner broker exports still needed for actual household/summer-house parity.
The conservative consumer requests current quarter through next local-day end, so
it defers new planning while next-day prices are incomplete. No silent fallback.
See docs/price-engine-consumer.md for contract/test setup and limitations.

No Node-RED baseline, live HA, vehicle/charger control, stable release, merge or
production cutover changes. Continue with PR/CI evidence and update this same handoff.

## Previous tested PR #12 context (retained for provenance)

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
  validated at `6f972a554920ccd958ba4a77ccfa2147fd4c5b3f`: **138 passed, zero
  skips; 91% coverage**, Ruff/format and official local hassfest passed. All SIX
  exact-head remote push/PR checks passed: tests, hassfest and HACS. It prevents
  midnight cache reads consuming afternoon verification of morning source updates.
  The following handoff-only commit records these results; substantive code is unchanged.
- Source/component draft PR #12 (https://github.com/NicolaiTandrup/HA-EV-Charge-Manager/pull/12) is open from the active branch to
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

1. Wait for/resolve owner contract and read-only comparison inputs below.
   All substantive implementation checkpoints have passed exact-head CI.
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
gh pr checks 12 --repo NicolaiTandrup/HA-EV-Charge-Manager
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

Cloud networking: additive Datahub/Radius research hosts were saved to the cloud
configuration draft, preserving GitHub/package rules. Current access works, but
future snapshot reuse requires reviewing/saving and publishing the cloud environment
configuration (not an integration release). No secret requirements were added.
