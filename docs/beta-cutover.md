# Owner-supervised PE + CM migration and rollback

This is a preparation/runbook, **not authorization to execute it**. Do not modify
production HA, Node-RED, Tesla or Easee during development. Prerelease publication,
physical command tests and the actual cutover each need owner authorization.

## Offline evidence before the maintenance window

The legacy Energy Price Broker uses old HACS Nordpool; PE uses official HA Nord
Pool. **Do not require simultaneous operation of those brokers/integrations.**
Save legacy outputs/inputs and known-good plans before changing the dependency.
The original Brain v1.0 and Optimizer v1.2 exports are preserved byte-identically
under node-red/. Full Energy Price Broker v2.2 export and real recorded outputs
are missing from this workspace; issue excerpts are not an executable substitute.
Five original JavaScript planner cases run in CI, but full household broker parity
and physical command traces remain unverified. Never claim otherwise.

Export representative normal/negative/high-price slots, weekdays/weekends and
92/96/100-quarter days where available. Keep raw household data in owner-controlled
storage. Include the actual dated contract/DSO/VAT, source versions and timezone.
EWII household invoices verify only their billed household/period; they cannot
establish another site's/current markup. No raw invoice verification is claimed.

A normalized **offline comparison file**, separate from public API v1, contains:

```json
{"schema_version":1,"site_id":"synthetic","timezone":"Europe/Copenhagen","currency":"DKK","unit":"DKK/kWh","vat_included":true,"slots":[{"start":"2026-10-24T12:00:00+00:00","end":"2026-10-24T12:15:00+00:00","final_price_incl_vat":1.25}]}
```

Normalize recorded outputs without adding VAT or guessing missing prices. Compare
recorded legacy final totals with independently generated PE outputs for the same
historical site/date/configuration in an isolated test setup:

```sh
python scripts/compare_price_exports.py /private/legacy.json /private/candidate.json
```

The tool performs no fetching/composition/HA access. Missing/extra slots, identity,
units/VAT ambiguity and price differences fail. Default numeric tolerance is
0.000001 DKK/kWh, distinct from the optimizer's 0.005 price-ranking tolerance.
A passed comparison establishes only those recorded slots, not live readiness.
Preserve known-good schedules and compare optimizer staged priorities, deadline
margins, Cheap Boost and shared-site limits using recorded vehicle inputs too.

## Readiness gates (currently incomplete)

- PE native source configuration verified per actual site, exact inclusive units,
  no duplicate tariff/VAT, complete future coverage, midnight/startup recovery and
  independent API v1 readiness demonstrated on target HA OS/provider versions.
- CM entity mappings/manual corrections reviewed for every actual vehicle/charger;
  Custom/Fleet are the same logical vehicle where verified. Freshness, mixed-source
  snapshot consistency, site association and all simultaneous sessions verified.
- Actual installed Tesla/Easee capabilities and responses verified; mapped entity
  state is not proof of energy delivery. Unknown/stale/conflicting data must inhibit
  commands. No wakeups or duplicate ambiguous writes; verify API budget observations.
- Dormant executor still needs durable per-device commissioning, persisted uncertain
  command recovery and verifiable single-controller handover before transport wiring.
  Mock tests alone do not satisfy these gates. See command-executor.md.
- Explicit physical-session continuity across outages, unplug/replug races, multi-day
  zero-power guests and manually authorized unknown cars tested. Preview restart
  revokes guest authority conservatively because missed unplug cannot be disproved.
- Target-device backup/restore, abort observation and rollback rehearsal completed.

## Coordinated owner-approved window

1. Take full HA/Node-RED backups and export the **actual** three production flows,
   helper/entity/service mappings and old HACS Nordpool version/configuration.
   Record last known good prices, SoCs, sessions, charge limits and controller state.
2. Confirm owner's explicit approval and inventory every command-producing path.
   Disable, **do not delete**, legacy Brain, Energy Price Broker and Charger
   Optimizer flows together as appropriate. Verify stopped writers before granting
   a new owner; never allow both Node-RED and CM to command a physical charger/car.
3. Switch the Nord Pool dependency in the planned window, preserving the exact old
   integration for rollback. Configure official Nord Pool → PE; verify actual units,
   VAT, dates, complete quarters, current/next day and site pricing configuration.
4. Configure CM's explicit PE mapping and devices; keep control disabled. Check
   source freshness, site/electrical limits, guest handling, forecasts and history.
   Missing prices are never zero; an offline parity pass does not bypass readiness.
5. Only after separate reviewed transport/hardware acceptance and owner's deliberate
   per-vehicle **and** per-charger commissioning may a future control-capable build
   be activated. Start with an isolated resource if single ownership can be proven.
   The present preview cannot be activated for real commands through its UI.
6. Observe real acknowledgments, actual power/SoC/current, budget and source health.
   Abort on conflicting ownership, wrong vehicle/site, stale data, unexplained prices,
   unknown command outcome or compromised guest protection. Never retry uncertainty
   through an alternate provider. Do not improvise unattended safety stop commands.

## Rollback

Disable CM control/transport first and verify it cannot send more commands. Restore
old HACS Nordpool and its exact configuration; verify its entities and known-good
broker output before re-enabling saved legacy flows. Re-enable one proven controller
only after dependencies and physical sessions are reconciled. Merely toggling
Node-RED back on while its old Nordpool integration is absent is not rollback.
Preserve PE/CM logs/history/backups for offline investigation; do not delete records
or reset guest authority silently. Record the owner, time and restored versions.
