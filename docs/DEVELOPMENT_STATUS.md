# Development handoff

Updated 2026-10-24. Read AGENTS.md, relevant issues/open PRs and inspect Git first.

## Owner architecture decision / PR stack

HA-Energy-Price-Engine is the authoritative producer. EV consumes final inclusive
prices only. Embedded pricing is **frozen migration/reference**, not a permanent
subsystem to expand. No new supplier/DSO/VAT/ledger/scheduling business work here.
ADR 004 supersedes the pricing ownership in earlier ADRs.

Existing unmerged drafts: #5 → #6 → #11 → #12 (last source checkpoint `9d949c6`).
EV consumer draft #13: branch `feat/authoritative-price-consumer`, code `3204a2f`,
based on #12. **152 tests passed**, Ruff/format/local hassfest passed; all exact-head
remote push/PR tests, hassfest and HACS passed.

Parallel implementation discovered during this session: producer draft **#7**
`feat/standalone-price-engine`, pinned head
`46b33bf50773082b6d942816c676dd098ee6bad1`, provides the actual public Python API v1.
Companion EV draft **#15**, head `0a28438`, exercises that API. Reuse its approach;
do not duplicate its branch or merge drafts. Prior service proposal EV #13 /
producer #6 is superseded; their earlier missing-runtime statements are historical.

Measured-history draft **#14**, `feat/measured-ev-history`, last handoff `e6dcbc6`,
code `8def346`: **168 tests passed, zero skipped, 91% coverage**, Ruff/format,
official local hassfest and all six exact-head remote push/PR checks passed.

Reconciliation draft **#16** is now published, branch `feat/reconcile-price-api-v1`,
head `23bf84b`, code `1fb09e2`. **176 tests, zero skipped, 91% coverage** plus
Ruff/format/local official hassfest passed. All six exact-head remote push/PR tests,
hassfest and HACS checks passed. GitHub authentication has recovered. Producer
proposal correction `edd4361` was pushed; correction comments posted on EV #14
and producer #6. No existing PR was merged or branch overwritten.

Provider policy draft **#17**, branch `feat/native-provider-policies`, head `c2a7a3d`:
183 tests passed, zero skipped, 92% coverage, Ruff/format and local hassfest passed.
All six exact-head remote tests/hassfest/HACS push/PR checks passed. Covers native
0/1/2/6 fleet setup, edits/removal, independent policies and duplicate charger rejection.

Dormant executor draft **#18**, branch `feat/mock-command-executor`, code `e49b357`:
191 local tests passed, zero skips, 92% coverage; Ruff/format/local hassfest passed.
All six exact-head remote push/PR tests, hassfest and HACS checks passed. No default
transport or live startup/service wiring; native review grants no control authority.
See docs/command-executor.md for actual authority/persistence/hardware acceptance gaps.

Verified-ranges draft **#19**, branch `feat/verified-price-ranges`, code `e484f5d`:
193 local tests passed, zero skips, 92% coverage; Ruff/format/local hassfest passed.
All six exact-head remote push/PR tests/hassfest/HACS checks passed. Independently
READY local-day ranges preserve today's usable prices before tomorrow publication.

Charger registry draft **#20**, branch `feat/charger-registry-configuration`, head
`4f2205f`: 196 local tests, zero skipped, 92% coverage, Ruff/format/local hassfest
passed. All six exact-head remote push/PR tests/hassfest/HACS checks passed. Native
charger discovery, registry-rename/reparent guards and site/departure policy fields
are complete for mocked/read-only review; physical adapter acceptance is unrun.

Calendar-history draft **#21**, branch `feat/calendar-measured-history`, code
`60d7880`: 200 local tests, zero skips, 92% coverage, Ruff/format/local hassfest
passed. All six exact-head remote push/PR tests/hassfest/HACS checks passed. New
observed date buckets support day/week/month/year entities, exact local-midnight
splitting, unpriced energy and negative cost. Legacy lifetime totals are not dated.

Active branch `feat/beta-readiness`, based on #21. Checkpoint subject
`Validate concurrent beta fleets and document reversible offline cutover`:
**210 local tests passed, zero skips, 92% coverage**; Ruff/format including scripts
passed. Official local hassfest passed (1 integration, 0 invalid). Remote checks pending
push; do not report them as passed until exact-head completion.
Failing regression exposed dangling active sessions after Options removal; fixed
by pruning only active references, retaining historical ledgers. Real HA tests
cover 0/1/2/6 concurrent vehicles/chargers/sites, explicit PE mapping, equal physical
ownership, per-site power bounds and zero physical calls. Replaced physical devices
cannot inherit guest session IDs/authority. Exact Tesla registry VIN duplicates and
conflicts fail closed, with native error explaining correct logical linking; no
names/network/fuzzy merges or VIN diagnostics. Missing VIN remains manual review.
Native capability review now supports charger-only devices as well as vehicles.

Installation and atomic cutover/rollback/hardware acceptance runbooks are under
`docs/beta-installation.md` and `docs/beta-cutover.md`. The offline price-export
comparison CLI is tested for exact/negative/zero prices, missing coverage, identity
and VAT ambiguity. It fetches nothing and calculates no tariffs. The original full
Energy Price Broker v2.2 export (tab epb_mqtt_tab_v22 / function epb22_build) and raw
household recorded outputs/invoices remain missing; no full household parity claimed.

**Readiness:** installable native read-only development candidate, NOT a live-control
beta or published prerelease. HACS metadata CI is validated; main has not been merged
and ordinary HACS candidate distribution needs separate owner-approved ref/release.
Dormant command executor needs durable per-device authority/uncertain-write recovery
and installed-version/hardware acceptance before live wiring. All drafts remain open.

## Completed (do not repeat)

- Prior vehicle registry/provider/snapshot, Brain guest/simulation and optimizer
  parity work stays intact. Original Node-RED exports remain byte-identical.
- Consumer v1 validation: explicit producer-entry/site identity, strict version,
  inclusive DKK/kWh, verification age/revision/range validation. Partial ranges
  never become fake zero prices. Stale/error/unloaded producers fail closed,
  including inside lookup throttle; duplicate events coalesce and rollback fails.
- New sites configure the independent producer in native UI; legacy pricing sites
  remain explicitly migration/reference, with no silent conversion or cutover.
  Consumer sites start no embedded fetch/composition/publication timers.
- Lookup hardening: per-site serialization, bounded once/minute retries, retained
  diagnostic reasons and earliest-price-tolerance regression. Actual API reads are
  synchronous in-memory lookups, with no transport timeout or live fetching.
- Native measured site/vehicle energy, known priced cost and unpriced energy.
  Price absence is not zero-cost charging. Actual measurement is independent of
  SoC/target/planner availability; new power reports only, no watchdog extrapolation.
  Source gaps/restarts/provider changes reset baselines. Negative prices are credits.
- One durable distance ledger per logical vehicle, km/mi normalization, registry-
  rename continuity and conservative provider/calibration rebasing. No multi-site
  duplicate distance. Invalid/nonfinite values and source resets are guarded.
- Physical Brain assignment gates site pricing: GPS cannot move an established
  session to another site. Optimizer simulation intents require a valid, fresh,
  correctly attributed plan and usable external prices. Guest protection remains.
- EV's own outputs cannot be circular vehicle inputs and perpetuate fake freshness.
- Regressions cover multi-day zero-power guest authorization, source gaps, missing
  SoC/GPS with valid measurement, unpriced persistence/restart, distance rename/
  provider switch, negative costs, site mismatch and producer contract failures.

## Real limitations / external prerequisites

Actual producer API/ledger interoperability is now tested using synthetic inputs:
92/96/100-quarter local days, negative prices, stale readiness and site isolation.
No source fetching or pricing calculation occurs on consumer reads. This is not
live two-instance HA/hardware acceptance. API v1 requires complete requested range;
EV queries local-date subranges through next-day midnight and retains only
independently READY ranges. Unpublished tomorrow no longer suppresses verified
today-only plans/history. Future refinement can scope requests to exact vehicle
deadlines and isolate historical settlement reads. Never accept partial producer
ranges as READY or restore embedded pricing as fallback.

Producer Issue #4 records household invoice-backed EWII markup **0.030 DKK/kWh ex
VAT for June–September 2026 only**. This resolves that historical fact only. Raw
invoices are absent from the workspace/checkouts: no raw-file verification or
private invoice fixture is claimed. Never infer current/later/other-site rates.
Invoice verification and pricing UI belong in the producer, not the EV consumer.

Power-derived history is an observation estimate, not certified/billing-grade.
Verify AC input boundary for delivered electricity costing. Missing telemetry is
not interpolated; cost coverage refers only to recorded energy. Historical price
backfill/accounting beyond the live measurement window needs an explicit settled
producer contract. Hardware/provider-brand acceptance remains unrun.

## Recommended next step

Publish beta-readiness draft based on #21, check exact-head CI and record results.
Then continue in this order, without redoing completed ports/configuration:

1. Add durable dormant-executor request/uncertainty audit storage and recovery tests,
   preserving no default transport/public enablement; define explicit physical-session
   reconciliation using verified installed-provider capabilities before any live wiring.
2. Broaden recorded Node-RED Brain/Optimizer action traces and actual brand/version
   capability fixtures. Full Energy Price Broker parity is blocked by its absent
   export/recorded outputs; use offline fixtures, never simultaneous live brokers.
3. Validate target HA OS/provider telemetry freshness, acknowledgments, per-device
   ownership and prolonged guest/unplug/offline behavior only in separately owner-
   authorized device trials. No unattended commands, production changes or prerelease.
4. Consider settled historical cost backfill only with explicit producer settlement
   semantics and immutable audit; never rewrite known measured costs silently.

Original Brain/Optimizer exports are available and unchanged. The complete original
Energy Price Broker v2.2 export/recorded outputs are **not present** in this workspace
or earlier repository source trees. Issue descriptions are not an executable oracle.
Document that offline parity gap; do not claim raw-invoice or full broker parity.
Continue independent work without reconstructing or modifying the live broker.

## Exact validation commands

From `/workspace/HA-EV-Charge-Manager`, existing Python 3.14.8 / HA 2026.10.2:

```sh
git status --short --branch
git log -6 --oneline
PRICE_ENGINE_SOURCE=/tmp/ev-price-producer-reference /workspace/ev-manager-venv/bin/python -m pytest --cov=custom_components.ev_charge_manager --cov-report=term
PRICE_ENGINE_SOURCE=/tmp/ev-price-producer-reference /workspace/ev-manager-venv/bin/python -m pytest tests/test_price_api_interop.py tests/test_price_consumer.py tests/test_measured_history.py tests/test_history.py tests/test_registry.py
/workspace/ev-manager-venv/bin/ruff check custom_components tests scripts
/workspace/ev-manager-venv/bin/ruff format --check custom_components tests scripts
docker run --rm -v /workspace/HA-EV-Charge-Manager:/github/workspace ghcr.io/home-assistant/hassfest
gh pr checks 21 --repo NicolaiTandrup/HA-EV-Charge-Manager
gh pr checks 22 --repo NicolaiTandrup/HA-EV-Charge-Manager
git diff --check
```

Node.js 24 is required for five real original Node-RED JavaScript parity cases;
zero skips in the last full run. Do not reinstall working dependencies. Local full
HACS container DNS is unavailable; actual remote HACS checks are the evidence.
CI checks out pinned producer source to ignored `price-engine-reference/`. Local
PRICE_ENGINE_SOURCE must point at an isolated export of the pinned producer commit.
See docs/contracts/price-consumer-v1.md for provenance and commands.

## Checkpoint safety

Update this same handoff, commit/push coherent changes, comment meaningfully and
check the exact head CI. A handoff cannot contain its own hash; use checkpoint
subject and exact prior validated hashes. No production Node-RED changes, live
HA/vehicle/charger commands, merge, stable release, deploy or cutover. Future real
commissioning remains per vehicle AND charger. No secrets/raw private invoices in Git.

Production export hashes verified unchanged at final checkpoint:
- Brain v1.0: `529bb37fb8c7dcc74e7cb0d73c48b8cf62034d8ba6ea8cade7c9ef1aee788965`
- Optimizer v1.2: `9d5bd42771539d08a584a94a5db7150bab7875afcb0c9d47e8528389ddc579ed`
