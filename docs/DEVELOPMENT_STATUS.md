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

Independent producer contract proposal: HA-Energy-Price-Engine PR #6, branch
`docs/ev-consumer-contract-v1`, commit `76fa1ab` based on main. Docs-only proposal,
not a runtime producer. Shared contract/example identical across repositories.
JSON parses and its synthetic example is exercised by EV decoder tests; producer
runtime/hassfest/HACS are unrun because no producer implementation exists.

Active EV branch `feat/measured-ev-history`, draft **#14**, based on #13.
Measured-history code `c38e915` passed **166 local tests** and all six exact-head
remote push/PR tests, hassfest and HACS.
Current follow-up subject `Validate producer mapping and require scheduled optimizer starts`:
validated at `8def3463f43765311eae791892aba43a777fa1d3`:
**168 tests passed, zero skipped; 91% coverage**; Ruff/format and official local
hassfest passed with zero invalid integrations. All six exact-head remote push/PR
checks passed: tests, hassfest and HACS. The following handoff-only commit records
this evidence; substantive code is unchanged.
It adds native producer-mapping validation and rejects Optimizer starts outside a
current proposed allocation, including already-complete targets. Do not merge stack.

## Completed (do not repeat)

- Prior vehicle registry/provider/snapshot, Brain guest/simulation and optimizer
  parity work stays intact. Original Node-RED exports remain byte-identical.
- Consumer v1 proposal: explicit producer-entry/site identity, strict version,
  inclusive DKK/kWh, verification age/revision/range validation. Partial ranges
  never become fake zero prices. Stale/error/unloaded producers fail closed,
  including inside lookup throttle; duplicate events coalesce and rollback fails.
- New sites configure the independent producer in native UI; legacy pricing sites
  remain explicitly migration/reference, with no silent conversion or cutover.
  Consumer sites start no embedded fetch/composition/publication timers.
- Further lookup hardening: per-site serialization, ten-second timeout, bounded
  retries, retained diagnostic reasons and earliest-price-tolerance regression.
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

Producer repo currently has README/LICENSE, requirements Issues #1–#5 and the
contract proposal only. **No get_prices runtime implementation exists.** EV tests
mock the service; actual two-runtime interoperability is NOT validated. Next: adopt
and implement the producer contract independently, then run shared conformance and
parallel-read tests. Do not recreate tariff ownership in EV to bypass this blocker.

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

Code CI is green for the measured-history draft. Next coordinate producer
PR #6 / Issue #5 adoption and actual API implementation. Extend consumer tests only
against the agreed version. Independent EV follow-ups: settled-history backfill,
verified brand capability metadata and broader parity fixtures; no live commands.
Do not repeat completed ports, pricing research, registry/consumer/history work.

## Exact validation commands

From `/workspace/HA-EV-Charge-Manager`, existing Python 3.14.8 / HA 2026.10.2:

```sh
git status --short --branch
git log -6 --oneline
/workspace/ev-manager-venv/bin/python -m pytest --cov=custom_components.ev_charge_manager --cov-report=term
/workspace/ev-manager-venv/bin/python -m pytest tests/test_price_consumer.py tests/test_measured_history.py tests/test_history.py tests/test_registry.py
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
Producer docs-only validation: `python -m json.tool docs/contracts/example-response-v1.json`.

## Checkpoint safety

Update this same handoff, commit/push coherent changes, comment meaningfully and
check the exact head CI. A handoff cannot contain its own hash; use checkpoint
subject and exact prior validated hashes. No production Node-RED changes, live
HA/vehicle/charger commands, merge, stable release, deploy or cutover. Future real
commissioning remains per vehicle AND charger. No secrets/raw private invoices in Git.
