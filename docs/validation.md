# Validation evidence

Development target: Home Assistant 2026.10.2, CPython 3.14.8, Node.js 24.19.0.
Development dependencies use the imported SHA-256-locked dependency set; deployment
adds no Python packages. `scripts/setup-cloud.sh` was exercised twice successfully.

Local checks on the implementation branch:

- **88 passed, zero skipped/failed** using pytest, including five scenarios executing
  the original Node-RED JavaScript planner rather than a rewritten oracle.
- **91% statement coverage overall**, planner 98%, Brain 99%, session model 100%.
- Ruff lint and formatting checks passed.
- Official `ghcr.io/home-assistant/hassfest` completed with **one integration,
  zero invalid integrations**. Initial manifest ordering/service-description
  failures were corrected and the real validator rerun successfully.
- HACS's own manifest and integration JSON schemas passed inside its official
  action container. GitHub Actions Tests, hassfest and full HACS checks also
  passed for the original guard implementation (`d41120f`) and the snapshot
  consistency slice (`e2bd6b3`), on both push and pull-request workflows.
  HACS validation is not catalog acceptance.
- Real HA config entry setup, independent module combinations, source events,
  freshness watchdog, config/options flows, unload and storage exercised.
- Official Nord Pool response service mocked at HA service boundary: DKK/MWh
  conversion, cached today/tomorrow, missing tomorrow, failure cooldown and tariff
  composition exercised through the unified coordinator.
- Per-field invalid/stale fallback, fresh-primary-off precedence, semantic discovery,
  foreign-device rejection and edit-preserved logical identity exercised.
- Snapshot skew boundary, missing/active power, contradictory charging/cable states,
  source priority, recovery and configurable/legacy defaults covered. Brain-only
  simulation remains independent of missing Optimizer fields. Nine new snapshot
  cases pass; full suite is 88 passed with zero skips. Fresh-read intent checks
  reject unsafe Optimizer inputs before pending coordinator events complete.
- Guest physical-session IDs, no-power persistence, restart reconciliation,
  physical-disconnect revocation and rapid disconnect/replug race covered.
- Command idempotency, owner conflicts, stale sessions, budgets and guest gates
  covered with simulation-only intents. Setup/update tests assert no HA service
  dispatch for entity-price workflows; official price workflows dispatch only the
  Nord Pool read service. No real hardware/API request is made by these tests.

Preserved Node-RED SHA-256 checksums match reviewed source checkouts:

```text
529bb37fb8c7dcc74e7cb0d73c48b8cf62034d8ba6ea8cade7c9ef1aee788965  EV-Charger-Brain-v1.0.json
9d5bd42771539d08a584a94a5db7150bab7875afcb0c9d47e8528389ddc579ed  EV-Charge-Optimizer-v1.2.json
```

No real HA installation, Tesla, Easee, household automation or Node-RED server was
contacted. No hardware acceptance, full behavioral parity, stable release, HACS
catalog inclusion or production migration is claimed. Keep Issues #1–#4 open for
the remaining acceptance work in [roadmap.md](roadmap.md).

Remote checks: [implementation PR checks](https://github.com/NicolaiTandrup/HA-EV-Charge-Manager/pull/6/checks).

## Later continuation checkpoints

- `f7a16e6`: 94 tests, including registry regressions first observed failing;
  remote tests/hassfest/HACS passed.
- `f488748`: 99 tests with provider management; remote checks passed.
- `d1c66b7`: 106 tests with persistent indexed prices; remote checks passed.
- `5c32dc9`: 114 tests with scheduled refresh; remote checks passed.
- `b9ce79a`: 136 tests with verified Radius/dated components; push checks passed.
- Latest pricing hardening: **137 passed, zero skipped; 91% statement coverage**;
  Ruff/format and official local hassfest pass. Check its pushed head for remote CI.

Live research contacted only public Datahub/Radius documentation and tariff assets,
not household HA or vehicle/charger services. ADR 003 records units, identity, VAT,
effective-date evidence and fixtures. Real household pricing parity remains unrun
pending the owner's contract and read-only broker comparison inputs.

Publication-cache follow-up: **138 passed, zero skipped, 91% statement coverage**;
Ruff/format and official local hassfest passed. The 09:00 Copenhagen publication
bucket prevents midnight refresh from suppressing a subsequent source verification.
`afe2e88` and exact follow-up head `6f972a5` both passed all push/PR tests,
hassfest and HACS. No household parity/hardware acceptance is claimed.

## Independent producer / EV history continuation (2026-10-24)

Consumer `3204a2f`: 152 local tests and all exact-head remote tests/hassfest/HACS
passed. Shared v1 producer example is synthetic; no actual producer runtime exists.
Latest measured-history checkpoint: **166 passed, zero skipped; 91% coverage**;
Ruff/format and official local hassfest passed. Remote results must be checked at
its pushed head. Includes source-report-based energy, explicit unpriced coverage,
negative costs, logical-distance attribution, guest/site guards and consumer parity.

No raw invoice files were available. The producer issue's 0.030 DKK/kWh ex-VAT
June–September 2026 household statement is historical scoped evidence only, not a
current contract/default or a raw-invoice conformance test.

Measured-history `c38e915` passed 166 tests and all exact-head remote push/PR tests,
hassfest and HACS. Follow-up adds native producer-entry mapping and out-of-window
Optimizer-start regressions: **168 passed, no skips; 91% coverage**, Ruff/format and
local official hassfest passed. Exact head `8def346` passed all six remote
push/PR tests, hassfest and HACS checks.
