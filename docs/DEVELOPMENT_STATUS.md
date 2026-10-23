# Development handoff

Updated 2026-10-23. Canonical continuation file; read AGENTS.md first.

## Active state

Branch `feat/unified-read-only-integration`, draft PR #6 stacked on architecture
PR #5. Baseline owner checkpoint was `4051ec0`; do not recreate completed work.
Current issues: #2 provider identity/management; next #9 persistent prices, #10
scheduled refresh, then #7 verified DSO and #8 dated components.

## Completed and validated

- Existing unified integration/snapshot guard: 88 tests, CI tests/hassfest/HACS
  passed at `4051ec0` / implementation `e2bd6b3`.
- `f7a16e6`: vehicle registry identity binding, verified device ownership on every
  read, persistent rename reconciliation without resetting sessions, deletion/name
  reuse protection. Four regressions observed failing before fix. Six registry
  cases and full **94 tests** pass. Remote push/PR tests, hassfest and HACS all passed.
- Current checkpoint `Add identity-preserving provider management controls`:
  reorder/promote/remove and explicitly remap replacement devices; preserves vehicle
  UUID, provider ID and priority when editing fields. Five UI cases and full
  **99 tests pass, zero skipped**; Ruff and official local hassfest passed.
  Remote CI must be checked after pushing this checkpoint.

## Current work / precise next step

Provider management is locally validated; push/check CI. Continue #9 by adding a
persistent per-site price table with atomic writes, immutable historic final prices,
source/component provenance, no-op unchanged updates, DST-complete day validation
and indexed lookup-only reads. Integrate consumers before scheduled refresh #10.
Then investigate actual structured Radius C source availability (#7) before writing
its adapter; no guessed identities/fees. #8 supplier markup is contract-specific.

## Remaining priorities and limitations

1. #9 persistent Fetch → Normalize → Calculate → Persist → Lookup architecture.
2. #10 publication schedule and startup recovery using persisted completeness.
3. #7 verified Radius C feed with safe cached/manual fallback; #8 dated components,
   separate component VAT and fixed subscriptions. Do not infer owner's EWII contract.
4. #2 verified actual brand capability metadata and upstream freshness; report-time
   consistency is not proof of an atomic upstream snapshot. Pricing/charger-status
   entity references are still strings; rename work so far covers vehicle providers.
5. Measured energy/cost/distance entities, richer site/currency configuration,
   broader parity and HA OS/Raspberry Pi observation.

Missing/unverifiable legacy vehicle entities now fail closed and require reviewed
remapping. Deleted/disabled/reassigned registry entries never silently bind by name.
Guest authority after HA downtime still requires reconfirmation. No live executor,
real probes, acknowledgment loop or production budget is implemented. Future real
commissioning is per vehicle AND charger. Node-RED remains byte-identical production
baseline. No merge, stable release, live commands or production cutover.

## Commands / evidence

From `/workspace/HA-EV-Charge-Manager`, existing Python 3.14.8 environment:

```sh
git status --short --branch
git log -5 --oneline
/workspace/ev-manager-venv/bin/python -m pytest
/workspace/ev-manager-venv/bin/python -m pytest tests/test_registry.py tests/test_provider_management.py
/workspace/ev-manager-venv/bin/ruff check custom_components tests
/workspace/ev-manager-venv/bin/ruff format --check custom_components tests
docker run --rm -v /workspace/HA-EV-Charge-Manager:/github/workspace ghcr.io/home-assistant/hassfest
gh pr checks 6 --repo NicolaiTandrup/HA-EV-Charge-Manager
git diff --check
```

Node.js 24 is required for five original Node-RED JavaScript parity cases. No skipped
parity run establishes parity. Do not reinstall working dependencies unnecessarily;
`scripts/setup-cloud.sh` refreshes the SHA-256 locked environment if needed. Local
full HACS container DNS is known unavailable; real remote HACS action passes.

At checkpoints update this file with actual results, commit/push coherent work,
comment on PR #6 when meaningful, and check its exact head CI. A handoff cannot
contain its own hash: use the checkpoint commit subject and exact prior validated
hashes. Reconstruct interrupted work from Git/PR/tests before repeating anything.
