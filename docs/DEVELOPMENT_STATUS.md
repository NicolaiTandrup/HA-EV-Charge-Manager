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

## In progress

Next code slice: snapshot consistency guard for Issue #2. No implementation of
that slice was present at this handoff checkpoint. Keep valid primary fields
preferred; do not silently switch to Fleet to hide contradictory observations.

## Remaining tasks, in priority order

1. Implement/test a conservative forecast guard for contradictory connection and
   charging fields and excessive report-time skew. Expose reasons/provenance and
   make the skew limit configurable. Do not claim HA timestamps prove upstream
   freshness or atomicity. Keep Brain physical-session semantics unchanged.
2. Registry rename/device replacement and provider reorder/remove UX, with stable
   logical identity. Validate actual brand metadata before adding brand adapters;
   no friendly-name guessing or unverified capability inference.
3. Broader parity and restart/source-mismatch cases; provider capability schema and
   write preferences as non-executing metadata, subject to architecture review.
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
- Report timestamps reflect HA reports, not upstream vehicle freshness. Temporal
  consistency guard design/validation remains unfinished.
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
/workspace/ev-manager-venv/bin/python -m pytest tests/test_manager.py -q
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

Read this handoff, inspect Git/PR #6 and Issue #2, then implement the snapshot
consistency guard described above. Add focused tests and use the existing HA
suite. Update this file with actual outcomes, commit/push the coherent slice,
and post one concise progress comment on PR #6. Never repeat the initial port,
setup, PR creation or completed baseline validation merely to rediscover it.
