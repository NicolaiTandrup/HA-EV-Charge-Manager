# PAHA02-DEV read-only acceptance

This guide targets a separate Raspberry Pi Home Assistant test instance, not the
production installation. A test VLAN does not prevent cloud Tesla/Easee writes.
The CM executor has no live transport by default; do not inject one or commission
physical control during this procedure.

## Installation gate

Normal HACS registration/download is **currently blocked**: both repositories'
default branches lack the integrations. Adding a `/tree/feature-branch` URL does
not select that branch in HACS. See [the distribution evidence and owner approval
choices](HACS_DISTRIBUTION.md). Metadata CI and the candidate ZIP do not prove
normal HACS installation. No default-branch change, merge or release is authorized.

If the owner chooses a manual, isolated test installation, back up the test HA
configuration, stop HA, and copy only the ZIP's
`custom_components/ev_charge_manager` directory into its `custom_components`
directory. Check the downloaded commit/artifact and restart HA. Do not copy test
configuration into production. Do not overwrite another installed version without
retaining its files and configuration backup. The candidate includes no provider
credentials, active transport, owner device IDs or production configuration.

## Native fixture preview — no providers needed

1. In Settings → Devices & services, add **EV Charge Manager**.
2. Leave vehicles, chargers and sites empty and finish the flow. Defaults are
   read-only; Brain and Optimizer can be toggled independently.
3. Open Configure → **Simulation scenario** and choose a friendly scenario name.
4. Inspect **EV Charge Manager / Simulation preview** and its `preview` attribute.
   It contains assignments, session explanations, proposed quarter-hour forecasts
   and headroom. `simulation_only` is true and `physical_commands` is zero.
5. Repeat with six vehicles, unknown guest, offline charger, location change,
   unexpected restart and simultaneous ambiguity. These are fictional portable
   fixtures, not the owner's household defaults or provider compatibility evidence.

Staggered plug traces permit reliable multi-car association without fixed car to
charger bindings. Simultaneous ambiguous plugs stay unresolved. The guest fixture
retains its simulated authorization for three days without a verified unplug.
Restart discards uncertain identity assumptions. Location change does not move an
existing physical plug reservation to another charger. Unknown occupied capacity
is conservatively withheld. No fixture result enters actual registry sources,
price mappings, measurement history, API budgets or command authorization.
The preview survives coordinator refresh, but not restart. Re-run it after restart.

Developer replay, using the project's installed Python/HA environment:

```sh
python scripts/replay_dev_scenarios.py --scenario six_vehicle_shared_sites \
  --at 2026-10-26T12:00:00+00:00 --output /tmp/cm-preview.json
```

The fixed time produces repeatable output. This CLI does not connect to HA. Its
fictional inclusive prices are for the preview only; they do not supply the live
optimizer and are not EWII tariff assumptions. The HA service
`ev_charge_manager.simulate_dev_scenario` offers the same own-state preview.

## Independent PE and read-only source acceptance

Install the independently reviewed PE candidate only through an approved test
installation route. Configure official Nord Pool in PAHA02-DEV, then a PE site.
In native CM configuration, select that exact producer entry and site for each
charging site. Inspect price-consumer readiness, complete quarter-hours, currency,
timezone and revision. There is no silent embedded-price/legacy-Nordpool fallback.
Test PE unavailable, late startup, restart and changed revision. The automated
coupled-runtime tests cover these without upstream requests; Pi OS, real Nord Pool
retrieval and installation remain owner-run acceptance checks.

To inspect physical sources later, explicitly choose reviewed registry devices
and correct ambiguous entity mappings in native Options. READ selection is
independent of WRITE selection. Discovery alone grants no control. Do not approve
Tesla OAuth/service access merely to run the isolated fixture preview.

## Record acceptance, then rollback

Record exact CM/PE commits, HA/HACS versions, Pi OS, source mappings, observed
readiness and any restart errors. Required unrun physical checks include actual
Custom/Fleet/Easee metadata, source availability/rename, sleep and delayed reports,
real meter accuracy, unplug/replug and guest continuity. Mock dispatch is not
physical acknowledgment or safe-control commissioning.

For a failed isolated installation, restore the retained files and configuration
backup with HA stopped, then restart and verify sources. For future production
migration use the separate [joint cutover/rollback checklist](beta-cutover.md):
atomic and reversible PE+CM cutover, never simultaneous legacy and PE brokers.
No production transition, live command, release or merge is performed by this guide.
