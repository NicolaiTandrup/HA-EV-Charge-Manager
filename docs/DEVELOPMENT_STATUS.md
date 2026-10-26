# Development handoff

Updated 2026-10-26. Read AGENTS.md, relevant issues/open PRs and inspect Git first.

## Latest validated continuation — native observations

Active branch `feat/native-planning-observations`, based on simulation PR #32
code `136d11d`. Subject `Expose reported targets and proposed charging decisions`.
**265 tests passed, zero skips, 93% coverage** with PE `bb715856`; Ruff/format and
official local hassfest passed (1 integration, 0 invalid). PR #32 all six remote
checks are green. Regressions failed first for the missing target observation.

Fresh reported target (including zero), earliest future rule deadline and next
proposed action now have dedicated read-only entities. Invalid forecasts report
blocked, not a command. No deadline is invented after its rule expires. Forecast
attributes correctly identify PE producer entry/site instead of legacy pricing.

Next: build/verify cumulative package, prepare non-destructive cumulative review
and check exact-head CI. Normal HACS and physical Pi/provider acceptance gates
remain unclosed; preserve all production Node-RED and keep transport absent.

## Latest validated continuation — portable simulation

Active branch `feat/paha02-simulation-preview`, based on observed-accounting
PR #31 code `54b25fc`. Subject `Preview portable multi-device scenarios without live input`.
**264 tests passed, zero skips, 93% coverage** with latest PE `bb715856`;
Ruff/format and official local hassfest passed (1 integration, 0 invalid).
PRs #29 and #31 now each have all six remote checks green, as do #27/#28/#30.

Native Options/service can run seven isolated deterministic fixture scenarios:
two Tesla/two Easee examples, six cars/shared sites, three-day guest, offline
charger, vehicle movement, restart and unresolved simultaneous ambiguity.
Results use the real Brain/planner/session implementations but never enter actual
registry, history, budgets or authority. Preview sensor and portable replay CLI
are included. `docs/paha02-dev.md` documents isolated installation and acceptance.

Next: finish missing read-only target/deadline/action observations, final candidate
package/consolidation and exact-head CI. Normal HACS distribution remains BLOCKED
by default-branch structure; manual ZIP is a separate isolated test route, not
normal HACS success. No live control, production transition, merge or release.

## Current extended-run continuation (2026-10-26)

Active branch `feat/native-access-policies`, based on validated #26 head
`5ef7115`. Reviewed #16–#26 stack: cumulative ancestry is preserved; #15 is the
parallel adapter reference, not a missing parent. No merges/rebases/branch deletion.
Latest public PE #7 is `bb71585654b431e61aa256657ab18d8c0f571cf0`; exported read-only
to /tmp/ev-price-producer-latest. Existing CI still pins the previous PE snapshot
until real cross-repository compatibility tests pass.

**Critical distribution correction:** normal owner HACS installation currently FAILS
for both repos because main only contains LICENSE/README. Latest PE handoff includes
actual PAHA02-DEV failure and executable HACS workflow evidence. A ZIP/manual smoke
test or green metadata check does not close this gate. See docs/HACS_DISTRIBUTION.md.
No main merge, default-branch change, new distribution repo, tag or release authorized.

Checkpoint subject `Configure native availability eligibility and charger limits`:
233 tests passed, zero skips, 93% coverage; Ruff/format and official local hassfest
passed (1 integration, 0 invalid). Regressions failed first for missing native
policy/disabled admission/charger cap. Existing defaults preserved. New native UI
supports disable, site/vehicle allowlists (empty restricted list denies all), explicit
charger site, manual/denied guest policy and optional maximum charger AC power.
Physical plug observation/demand conservatism/history remain; no permission or
command transport enabled. Remote checks pending publication.

Next independent work: native reviewed manual association, then immutable observed
session/charger accounting and latest PE API v1 entry scoping/fixtures. Add PAHA02-DEV
portable simulation fixtures and guide, additional concurrency/failure tests, rebuild
the cumulative ZIP and check exact-head CI. Do not repeat completed journal/provider
work or claim full normal HACS beta delivery before the distribution gate is approved.

## Reviewed manual association checkpoint

Policy draft **#27**, `feat/native-access-policies`, code `8c91e46`:
233 local tests, zero skips, 93% coverage, Ruff/format/local hassfest passed.
Remote results checked at this checkpoint; see PR #27 exact-head checks.

Active branch `feat/reviewed-manual-association`, based on #27. Subject
`Review manual vehicle identity for current simulated plug sessions`.
236 local tests passed, zero skips, 93% coverage; Ruff/format and official local
hassfest passed (1 integration, 0 invalid). Native Options chooses friendly labels,
captures session identity and rejects replug, stale/missing same-site evidence,
eligibility failure, guest takeover and another charger's reserved identity.
The helper/service only modifies own simulated state. Reviewed labels clear on
unplug/rapid replug and are not restored as authority across restart.
New PE initially failed the old interop fixture because its real SQLite ledger
shared the HA fixture directory across parametrized cases; next isolate that test
directory and validate strict producer-entry scoping against the new public API.
Do not expand producer logic in CM or bypass its stale-writer guard.

## Latest paired PE checkpoint

Manual-association draft **#28**, code `a9184a6`, passed 236 local tests and all
six exact-head remote tests/hassfest/HACS checks. Policy #27 code `8c91e46` is
also green. No source or branch history replaced.

Active branch `feat/latest-pe-contract`, based on #28. Subject
`Validate latest entry-scoped PE contract with coupled HA runtimes`.
**243 tests passed, zero skips, 93% coverage**, Ruff/format and official local
hassfest passed (1 integration, 0 invalid). CI pin advanced only after actual
tests passed to PE `bb71585654b431e61aa256657ab18d8c0f571cf0`.
CM passes producer_entry_id to v1 lookup, verifies result ownership and scopes
revision events. Regression rejects another entry's READY result and high foreign
revision. Actual SQLite tests use separate HA config dirs, not a shared fake store.
Exact producer-owned schema/examples are copied byte-identically and tested with
real serialized responses; read paths prohibit arithmetic/DB I/O/writes.
Reused PE coupled-runtime harness verifies producer-first/consumer-first startup,
late availability, future revisions/coalescing and unload with all HA services
forbidden. New remote checks pending publication.

Next: command multi-resource concurrency/fault audit, then session/charger accounting
with explicit observation boundaries, portable PAHA02-DEV fixture scenarios and
current-package rebuild. Normal HACS distribution remains blocked, not resolved
by these software tests. No repository-wide distribution action is authorized.

## Command concurrency/fault checkpoint

Active branch `feat/concurrent-command-journal`, based on paired-PE #29 code
`e19c944`. Subject `Persist concurrent device commands without cancellation races`.
**250 tests passed, zero skips, 93% coverage**; Ruff/format and official local
hassfest passed (1 integration, 0 invalid). New remote checks pending publication.
Failing concurrency regression showed unrelated devices blocked behind one network
wait; fixed with per-device operation locks and serialized write-only persistence.
A second failing regression exposed cancellation releasing the persistence lock
before a worker write finished; shielded completion now retains ordering and never
dispatches the cancelled request. Observation-only reconciliation never swaps a
shared transport. Durable per-intent audit and sanitized last-error diagnostics
persist; duplicate calls add no duplicate history. Imported invalid charger caps
NaN/infinite/nonpositive/non-numeric fail closed instead of falling back to vehicle
power; malformed guest policy does not grant simulated permission.

Next independent task: observed session/charger accounting with explicit missing
meter/estimate/continuity boundaries; reuse existing energy integration, never
double-integrate or reprice settled values. Then portable PAHA02-DEV fixtures and
current-package rebuild. HACS distribution remains a separately authorized gate.

## Observed accounting checkpoint

Command-concurrency draft **#30**, code `df25f84`, passed 250 local tests and
official local checks; remote results are tracked on its exact head.

Active branch `feat/observed-session-accounting`, based on #30. Subject
`Attribute observed charging deltas to immutable session segments`.
**256 tests passed, zero skips, 93% coverage**; Ruff/format and official local
hassfest passed (1 integration, 0 invalid). Remote checks pending publication.
Session/charger ledgers attribute existing history deltas, not a second integrator.
Segments split on replug/association/site/device/restart boundaries; closed costs
and price evidence are not rewritten. Unknown/missing guest meters are unavailable,
not free/zero. Native fixed per-charger active/lifetime/optional-period counters
expose estimates/unpriced coverage; detailed period entities are disabled by default
for new registrations to bound Recorder work. Histories and clock buckets retained.

A failing cached-report regression also fixed native restart baselines: pre-start
power timestamps cannot bridge downtime; require post-start reports. Source/gap/
snapshot guards still apply. Accounting uses verified atomic/cancellation-safe
writes; corrupt files preserved/unavailable. Tests use real isolated temporary HA
config files, never production. Next: portable native PAHA02-DEV fixture preview,
missing target/deadline/observed-enable diagnostics, final consolidated package.

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

Previous cumulative branch `feat/beta-readiness`, draft **#22**, based on #21. Checkpoint subject
`Validate concurrent beta fleets and document reversible offline cutover`:
**210 local tests passed, zero skips, 92% coverage**; Ruff/format including scripts
passed. Official local hassfest passed (1 integration, 0 invalid). Code checkpoint
`2aba16f` passed all six exact-head remote
push/PR tests, hassfest and HACS checks. The following handoff-only commit records
this evidence and corrects identity documentation; substantive code is unchanged.
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
Durable command recovery is now mock-tested in #23. Physical-session authority,
installed-version/hardware acceptance and live wiring remain unapproved. All drafts remain open.

## Current target: proposed v0.1.0-beta.1

Durable journal draft **#23**, branch `feat/durable-command-journal`, code
`3527c97`, is based on #22. **216 tests passed, zero skips, 92% coverage**,
Ruff/format and official local hassfest passed. All six exact-head remote push/PR
tests, hassfest and HACS checks passed. Disk-verified write-ahead reservations,
persistent ownership/idempotency/estimates and explicit read-only recovery replace
memory-only uncertainty. Corrupt/failed storage inhibits execution and is preserved.
Startup loads diagnostics with transport disabled; restart never replays.

Provider profiles draft **#24**, branch `feat/provider-adapter-profiles`, code
`58e0d3c`: **220 tests passed, zero skips, 92% coverage**, Ruff/format/local
hassfest and all six exact-head remote checks passed. Profiles use HA Fleet
2026.10.2 and pinned public Custom/Easee sources; docs/provider-adapters.md records
evidence. Location excludes destination/route; absent translation keys are handled
only through verified whole vendor unique-ID contracts. Manual overrides remain.

Previous packaging branch `feat/beta-candidate-package`, draft **#25**, based on #24. Checkpoint subject:
`Package proposed read-only beta and validate native status and legacy parity`.
**227 tests passed, zero skips, 93% coverage**; Ruff/format including scripts passed.
Official local hassfest passed (1 integration, 0 invalid). Code checkpoint
`6a337833f9124fca4e4c60eb3c693661444f1014` passed all six exact-head remote
push/PR tests, hassfest and HACS checks. CI review artifact is confirmed by API:
run 40177165226, artifact 12592382233, unexpired, matching code head. The artifact
storage redirect returned HTTP 403 during optional round-trip download, so CI/local
byte identity is not claimed; local rebuild determinism is tested. Local archive SHA-256:
`0e614e3f64347cadcc6d0a21e5eb950e6c021879298f64a0812b361408f05dc5`. Manifest is now proposed 0.1.0-beta.1; no tag or release is created.
The following handoff-only commit records this validation; substantive code is
unchanged. A deterministic allowlisted installable ZIP is built by
`python scripts/build_beta_candidate.py` into ignored dist/; CI retains a review
artifact for 14 days. Tests verify ZIP integrity/reproducibility, complete runtime,
packaged Python compilation, metadata and no cache/storage inclusion.

Native dedicated charger status/association, reported charging power and command
disabled/recovery/blocked entities supplement existing planned/history entities.
Native site save verifies PE entry ownership before accepting a mapping. A provider
with no read fields can be reviewed as WRITE-only without granting control.
These regressions failed first, then passed. Eight real JavaScript oracle cases
now run: five optimizer + three Brain. Brain fixture documents the Issue #3-approved
difference from the legacy defaultCar guess; no ambiguous native mapping is invented.
Node-RED files remain byte-identical. Full old broker/raw invoices remain absent.

Readiness is **packaged native read-only beta candidate**, with mock-tested journal-
backed dispatch/recovery, not approved live control or a published prerelease.
Normal HACS version distribution still needs a separately owner-approved ref/release;
the source ZIP and CI artifact allow review/test installation without merging main.

## Active checkpoint: final proposed beta.1

Packaging draft **#25**, head `1246ccf` (code `6a33783`), passed all six
exact-head remote checks. Its package is superseded by this safety follow-up.

Active branch `feat/verified-command-reconciliation`, draft **#26**, based on #25.
Checkpoint subject `Keep durable uncertainty latched until verified acknowledgment`.
**228 tests passed, zero skips, 93% coverage**; Ruff/format and official local
hassfest passed (1 integration, 0 invalid). Code `c650c6f` passed all six exact-head
remote push/PR tests, hassfest and HACS checks. CI built the superseding review
artifact in run 40177571289. The following handoff-only commit records this evidence;
substantive code is unchanged.
A failing regression demonstrated that an optimistic matching HA switch echo
could release the live journal latch. Native durable execution now retains pending
requests until explicit physical-session AND independent-acknowledgment attestations
plus a post-load/attempt fresh matching report. Mere HA echoes, service success,
duplicate keys or another provider cannot clear it. No public authority-grant or
reconcile service/transport wiring was added. Actual attestation must be verified
in separately authorized hardware trials; test flags are not security proof.

Build the latest branch's ZIP; do not install an earlier #25 artifact as though it
contained this hardening. The archive path stays dist/ev-charge-manager-v0.1.0-beta.1.zip
and the current local SHA-256 is
`ff692b6f3b15c187e09d6435479b8923234eb52e0ebad175f77af47913ba45c6`. No release/tag/main merge/live commands.

Latest coherent checkpoint subject: `Reject empty journal envelopes and invalid persisted bindings`.
The real-file failure matrix also covers valid JSON with null data and missing/
invalid physical binding fields: existing files cannot masquerade as a fresh
installation. **228 tests passed, zero skips, 93% coverage**, Ruff/format and
official local hassfest passed after this hardening; the local ZIP was rebuilt.
Earlier c650c6f and handoff 0a79de6 checks were green. Check the exact latest head's
remote receipt on PR #26 (tests/hassfest/HACS plus uploaded candidate artifact);
that receipt is posted after CI finishes without changing runtime code again.

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

Check the candidate branch head, artifact and exact-head CI first. Do not redo the
completed journal, provider profiles, native UI, multi-site/history or packaging.

Remaining real-device acceptance gates (not performed or authorized):
- Verify target HA OS and exact installed Custom/Fleet/Easee versions, permissions,
  source cadence/upstream timestamps, actual entity/service semantics and units.
- Verify physical charger session continuity across outages/unplug/replug before
  binding any real commissioning authority or clearing uncertainty. Internal test
  flags and optimistic HA switch reports cannot prove physical acknowledgment.
- Owner-supervised per-vehicle AND per-charger commissioning, single-controller
  handover, actual energy/current/SoC acknowledgment, timeout/guest/budget behavior,
  and rollback rehearsal; no unattended commands or production modifications.
- Obtain full legacy Energy Price Broker v2.2 export (epb_mqtt_tab_v22 / epb22_build)
  and recorded household fixtures for offline parity. Do not run both Nord Pool
  brokers together or infer current tariffs from historical EWII invoices.
- Ordinary HACS release/version publication and actual atomic cutover require
  separate owner approval. Do not create tags/releases or merge to bypass this.

Independent follow-up: settled historical cost backfill only with explicit producer
settlement/audit semantics; never silently rewrite measured costs or old dates.
Installation and joint atomic cutover/rollback gates: docs/beta-installation.md,
docs/beta-cutover.md, docs/command-executor.md and docs/provider-adapters.md.

## Exact validation commands

From `/workspace/HA-EV-Charge-Manager`, existing Python 3.14.8 / HA 2026.10.2:

```sh
git status --short --branch
git log -6 --oneline
PRICE_ENGINE_SOURCE=/tmp/ev-price-producer-latest /workspace/ev-manager-venv/bin/python -m pytest --cov=custom_components.ev_charge_manager --cov-report=term
PRICE_ENGINE_SOURCE=/tmp/ev-price-producer-latest /workspace/ev-manager-venv/bin/python -m pytest tests/test_price_api_interop.py tests/test_price_consumer.py tests/test_measured_history.py tests/test_history.py tests/test_registry.py
/workspace/ev-manager-venv/bin/ruff check custom_components tests scripts
/workspace/ev-manager-venv/bin/ruff format --check custom_components tests scripts
docker run --rm -v /workspace/HA-EV-Charge-Manager:/github/workspace ghcr.io/home-assistant/hassfest
gh pr checks 24 --repo NicolaiTandrup/HA-EV-Charge-Manager
gh pr checks 26 --repo NicolaiTandrup/HA-EV-Charge-Manager
git diff --check
```

Node.js 24 is required for original Node-RED JavaScript parity cases;
eight oracle cases and zero skips in the last full run. Do not reinstall working dependencies. Local full
HACS container DNS is unavailable; actual remote HACS checks are the evidence.
CI checks out pinned producer source to ignored `price-engine-reference/`. Local
PRICE_ENGINE_SOURCE must point at an isolated export of the pinned producer commit.
See docs/contracts/price-consumer-v1.md for provenance and commands. If the local
producer export is missing, recreate it without changing either checkout:

```sh
mkdir -p /tmp/ev-price-producer-latest
git -C /workspace/HA-Energy-Price-Engine archive bb71585654b431e61aa256657ab18d8c0f571cf0 | tar -x -C /tmp/ev-price-producer-latest
```

If pinned source is unavailable, fixture-only development remains possible using
`python -m pytest --ignore=tests/test_price_api_interop.py --ignore=tests/test_shared_pe_fixtures.py --ignore=tests/test_two_runtime.py`; report actual producer
conformance as unrun in that mode. Do not replace the version pin with a moving head.

## Checkpoint safety

Update this same handoff, commit/push coherent changes, comment meaningfully and
check the exact head CI. A handoff cannot contain its own hash; use checkpoint
subject and exact prior validated hashes. No production Node-RED changes, live
HA/vehicle/charger commands, merge, stable release, deploy or cutover. Future real
commissioning remains per vehicle AND charger. No secrets/raw private invoices in Git.

Production export hashes verified unchanged at final checkpoint:
- Brain v1.0: `529bb37fb8c7dcc74e7cb0d73c48b8cf62034d8ba6ea8cade7c9ef1aee788965`
- Optimizer v1.2: `9d5bd42771539d08a584a94a5db7150bab7875afcb0c9d47e8528389ddc579ed`
