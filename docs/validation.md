# Validation evidence

Development target: Home Assistant 2026.10.2, CPython 3.14.8, Node.js 24.19.0.
Development dependencies use the imported SHA-256-locked dependency set; deployment
adds no Python packages. `scripts/setup-cloud.sh` was exercised twice successfully.

Local checks on the implementation branch:

- **79 passed, zero skipped/failed** using pytest, including five scenarios executing
  the original Node-RED JavaScript planner rather than a rewritten oracle.
- **90% statement coverage overall**, planner 98%, Brain 99%, session model 100%.
- Ruff lint and formatting checks passed.
- Official `ghcr.io/home-assistant/hassfest` completed with **one integration,
  zero invalid integrations**. Initial manifest ordering/service-description
  failures were corrected and the real validator rerun successfully.
- HACS's own manifest and integration JSON schemas passed inside its official
  action container. GitHub Actions Tests, hassfest and full HACS checks also
  passed for the initial implementation (`406174e`); final guard updates run the
  same checks on the PR. HACS validation is not catalog acceptance.
- Real HA config entry setup, independent module combinations, source events,
  freshness watchdog, config/options flows, unload and storage exercised.
- Official Nord Pool response service mocked at HA service boundary: DKK/MWh
  conversion, cached today/tomorrow, missing tomorrow, failure cooldown and tariff
  composition exercised through the unified coordinator.
- Per-field invalid/stale fallback, fresh-primary-off precedence, semantic discovery,
  foreign-device rejection and edit-preserved logical identity exercised.
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
