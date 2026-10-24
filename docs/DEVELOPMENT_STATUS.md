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

Active reconciliation branch `feat/reconcile-price-api-v1`, based on #14. Checkpoint
subject `Reconcile measured EV consumer with producer-owned API v1`:
**176 tests passed, zero skipped, 91% coverage**; Ruff/format passed. Official local
hassfest passed (1 integration, 0 invalid). Code committed at `1fb09e2`.
**Push blocked:** GitHub credentials expired (`could not read Username`; API HTTP
401 Bad credentials). No reconciliation PR was created, no new remote CI ran, and
correction comments could not be posted. Branch and all work are local/committed.
Restore authentication, push and create a draft based on #14 before further changes.
Producer docs-only PR #6 branch has a separate local correction commit marking
its service proposal superseded by #7; push that correction too.
Three actual producer DST regressions failed before the fix (missing public lookup),
then passed. Tests use a pinned isolated producer export, no live sources or hardware.
This checkpoint preserves all measured-history work while replacing the obsolete
service transport/event with actual API v1 and verified durable entry/site ownership.

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
EV conservatively queries the recent measurement window through next-day midnight.
Before tomorrow's prices publish this can suppress otherwise feasible today-only
plans; next work should scope scheduling queries to relevant vehicle deadlines,
while keeping measured-current-price access separate. Never accept partial ranges
as READY or restore embedded pricing as fallback.

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

Restore GitHub authentication, then run:

```sh
git push -u origin feat/reconcile-price-api-v1
gh pr create --repo NicolaiTandrup/HA-EV-Charge-Manager --base feat/measured-ev-history --head feat/reconcile-price-api-v1 --draft --title "Reconcile measured EV consumer with producer-owned API v1" --body-file /tmp/ev-api-pr.md
```

Reconstruct the PR body from this handoff if the temporary file is gone. Update
EV #13/#14/#15 and producer #6/#7/Issue #5 with the supersession/interop evidence.
Push producer docs correction on `docs/ev-consumer-contract-v1` as well. Never merge.
Check exact-head remote tests/hassfest/HACS, then scope consumer queries to actual planning
needs and separate current measured-cost lookup. Reuse real producer pinned tests,
including today's usable range before next-day publication and cross-midnight/DST
vehicle deadlines. Independent follow-ups: settled-history backfill, verified brand
capability metadata and broader parity fixtures; no live commands. Preserve #14's
history/site/guest safeguards and #15's actual producer contract. Do not repeat ports.

## Exact validation commands

From `/workspace/HA-EV-Charge-Manager`, existing Python 3.14.8 / HA 2026.10.2:

```sh
git status --short --branch
git log -6 --oneline
PRICE_ENGINE_SOURCE=/tmp/ev-price-producer-reference /workspace/ev-manager-venv/bin/python -m pytest --cov=custom_components.ev_charge_manager --cov-report=term
PRICE_ENGINE_SOURCE=/tmp/ev-price-producer-reference /workspace/ev-manager-venv/bin/python -m pytest tests/test_price_api_interop.py tests/test_price_consumer.py tests/test_measured_history.py tests/test_history.py tests/test_registry.py
/workspace/ev-manager-venv/bin/ruff check custom_components tests
/workspace/ev-manager-venv/bin/ruff format --check custom_components tests
docker run --rm -v /workspace/HA-EV-Charge-Manager:/github/workspace ghcr.io/home-assistant/hassfest
gh pr checks 13 --repo NicolaiTandrup/HA-EV-Charge-Manager
gh pr checks 14 --repo NicolaiTandrup/HA-EV-Charge-Manager
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
