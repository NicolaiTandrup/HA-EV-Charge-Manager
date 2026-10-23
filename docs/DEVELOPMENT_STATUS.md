# Development handoff

Updated: 2026-10-23. This file is the canonical continuation point; do not create
another root-level DEVELOPMENT_STATUS.md.

## Current feature and Git state

- Product: unified native `ev_charge_manager`, read-only developer preview.
- Active branch: `feat/unified-read-only-integration`.
- Architecture/baseline draft: [PR #5](https://github.com/NicolaiTandrup/HA-EV-Charge-Manager/pull/5),
  branch `feat/unified-architecture`, based on `main`.
- Implementation draft: [PR #6](https://github.com/NicolaiTandrup/HA-EV-Charge-Manager/pull/6),
  stacked on `feat/unified-architecture`. Keep both drafts unmerged.
- Relevant requirements: Manager Issues #1–#4; active next slice is Issue #2,
  mismatched provider snapshots. Read current issue/PR changes before continuing.
- Last successful implementation commit: `d41120fa181d00cfb04f2dce51375e998d328746`.
  Local: 79 tests passed, no skips; Ruff passed. GitHub push and PR checks for that
  exact head all passed: tests, hassfest and HACS. Confirmed on continuation.
- Worktree was clean at continuation. No previous DEVELOPMENT_STATUS.md existed.
- Permanent handoff workflow committed as `616567d`. Current snapshot guard slice
  (commit subject `Guard inconsistent vehicle snapshots before forecasting`) is
  locally validated: **88 passed, zero skipped; 91% coverage; Ruff passed; official
  hassfest: one integration, zero invalid**. Remote CI for this new slice is pending
  until pushed; do not substitute the earlier green head as its CI evidence.

## Completed and validated

- Ported both native draft PR #2 engines/tests/docs with provenance. Preserved both
  Node-RED exports byte-for-byte; original source repositories remain unchanged.
- Shared logical vehicle registry, per-field freshness/fallback, reviewed semantic
  discovery, explicit overrides, source provenance and identity-preserving edits.
- Independently enabled Brain/Optimizer, bounded passive unique matching, durable
  simulated plug sessions, manual guest/probe simulations, centralized simulated
  ownership/idempotency/budget guards; no live command transport.
- Official HA Nord Pool read adapter/cache, all-in fixed/scheduled tariffs,
  independent sites, guest-load derating and staged 15-minute/07:00 forecasts.
- Unknown/offline reserved guest demand cannot be assumed zero. Guest authorization
  reconciles pending known-car updates; unplug/replug revokes simulated authority.
- Native config/options, sensors, anonymous diagnostics, English translations,
  brand assets, hashed development dependencies and GitHub CI.
- Established permanent session/checkpoint instructions in AGENTS.md. Documentation
  changes need no application test rerun; implementation evidence above is retained.
- Implemented Issue #2 snapshot consistency guard: configurable HA report-time
  skew (default 120 seconds, compatible with missing legacy setting), required
  forecast fields, active-power checks and charging/cable contradictions. Preserves
  per-field provider priority and physical sessions; exposes local health/provenance
  and anonymous issue counts. Optimizer simulation intents use fresh health reads;
  Brain-only simulation does not depend on SoC/target fields.
- Nine additional snapshot cases validated, including recovery and both independent
  Brain toggle states. No vehicle polling, wakeup, command transport or live trial.

## In progress

Snapshot guard implementation and local validation are complete. Push the coherent
slice and check PR #6's exact head. Record its remote CI outcome in this handoff;
then continue the first remaining task below. Do not rerun the port or initial setup.

## Remaining tasks, in priority order

1. Registry rename/device replacement handling with stable logical identity and
   fail-closed device ownership. Start with a regression test for a configured
   source entity being renamed in HA's entity registry. Current string entity IDs
   become unavailable until manually remapped; automatic repair is not implemented.
2. Provider reorder/remove/replacement UI and verified brand capability metadata.
   Do not infer identity/capability from display names or suffixes. Preserve UUIDs
   and safety checks when changing provider devices or source mappings.
3. Broader parity/restart/provider disagreement cases and verified upstream freshness.
   HA report-skew checks are now implemented but do not establish atomic snapshots.
4. Native measured energy/cost/distance entities using retained tested history,
   richer tariff calendars/currencies, overlapping-site configuration.
5. Hardware observation on HA OS/Raspberry Pi and real provider reporting cadences
   requires owner-coordinated access; no cloud task should contact live controls.

## Decisions, limitations and blockers

- No current tooling blocker: Git read/push/API and remote CI were working at the
  last validated head. Local full HACS container cannot resolve API DNS, but real
  GitHub HACS action passed. Do not repeat local networking troubleshooting.
- Future real commissioning is per vehicle AND charger (owner decision).
- Guest authority loses authorization after HA downtime because missed physical
  unplug cannot be disproven; stable session IDs alone do not prove continuity.
- Report timestamps reflect HA reports, not upstream vehicle freshness. The new
  temporal consistency guard is validated locally but is deliberately conservative;
  operators may need to configure its window for verified provider reporting cadence.
- No live executor, acknowledgments, persistent production budget or real probes.
  These require separate review/owner-supervised safety validation.
- Existing architecture, safety boundaries and production Node-RED baseline stand.
  Issues #1–#4 remain open. No merge, stable release, deployment or cutover occurred.

## Exact validation commands

From `/workspace/HA-EV-Charge-Manager`:

```sh
git status --short --branch
git log -5 --oneline
# Only refresh dependencies if absent/outdated (already prepared in this machine):
bash scripts/setup-cloud.sh
# Normal validation using existing environment:
/workspace/ev-manager-venv/bin/python -m pytest
/workspace/ev-manager-venv/bin/python -m pytest tests/test_manager.py tests/test_snapshot.py -q
/workspace/ev-manager-venv/bin/ruff check custom_components tests
/workspace/ev-manager-venv/bin/ruff format --check custom_components tests
docker run --rm -v /workspace/HA-EV-Charge-Manager:/github/workspace ghcr.io/home-assistant/hassfest
gh pr checks 6 --repo NicolaiTandrup/HA-EV-Charge-Manager
git diff --check
```

Python 3.14.8/HA 2026.10.2 and Node.js 24 are prepared. Node is required for five
real JavaScript Node-RED parity tests; a skipped parity run is not parity evidence.
See docs/validation.md for baseline evidence and docs/roadmap.md for broader scope.

## Recommended next action

Read this handoff, inspect Git/PR #6 and Issue #2, and confirm remote CI for the
latest snapshot guard commit before new code. Next, add a failing HA registry-rename
regression test and implement stable source-reference reconciliation with ownership
validation. Preserve provider priorities/logical UUIDs and fail closed if a device
cannot be verified. Update this file with evidence, commit/push the coherent slice,
and post one progress comment on PR #6. Do not repeat the initial port/setup/PR
creation or the completed snapshot guard work.
