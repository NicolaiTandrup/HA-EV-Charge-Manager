# Installing and configuring the development candidate

This is an installable **read-only development candidate**, not an approved live
controller or published beta release. The complete candidate is the head of the
current stacked draft in DEVELOPMENT_STATUS.md; main is not the implementation.
No PR in the stack has been merged. Do not install an earlier parent and expect
later fixes. Pin and record the reviewed producer and consumer commits together.

## Test installation

1. Back up the test HA instance. Use a supported HA version (current tests use
   HA 2026.10.2/Python 3.14.8) with the official Nord Pool integration for PE.
   No Tesla SDK is installed by CM; provider integrations already own telemetry.
2. Install the reviewed PE candidate in a test instance following its own docs.
   Configure site-specific DSO/supplier/tax/VAT and dated sources there. Verify
   READY status/coverage before CM optimization. No household example is a default
   tariff for another site or period.
3. Copy only `custom_components/ev_charge_manager` from the reviewed CM checkout
   into `/config/custom_components/ev_charge_manager` on that **test** instance.
   Restart it, then add EV Charge Manager under Settings → Devices & services.
   This document authorizes no action on the owner's production instance.
4. The HACS manifest/metadata and remote HACS validation pass. Ordinary HACS custom
   repository/version installation needs an owner-approved distributable ref or
   prerelease containing the complete integration. None is published by this work;
   do not imply that unmerged branch code is available on main. Once approved,
   add this repository as an Integration custom repository in HACS, select the
   reviewed candidate version, download and restart. Never enable automatic
   production upgrades from a changing development branch.

## Native configuration

- Add 0..N logical vehicles and fill capacity/max AC power/efficiency. IDs remain
  stable across edits; names are labels, not physical identity. An optional sensor
  can provide an offset-aware ISO departure timestamp. Existing planner stage and
  long-trip rules remain the baseline; do not change them through invented thresholds.
- Add each vehicle's HA provider devices through Provider, review semantic field
  suggestions and correct individual fields. Link Custom/Fleet representations of
  the same verified vehicle to the **same** logical vehicle. One device cannot be
  assigned to two logical identities. Ambiguous semantic matches remain unresolved.
- Set READ/WRITE preferences and independent fallbacks in Provider policies.
  Per-field/capability overrides remain editable. Defaults never hardcode ElLingo,
  Blue Flux, Tesla Custom or Fleet. READ fallback uses already reported HA states;
  CM does not refresh/wake vehicles. WRITE policy grants no control authority.
- Discover or add each charger, review its device-owned status and site/zone.
  One physical device has one logical controller; registry-bound mappings survive
  renames and reject device reassignment. Multiple vehicles can use a charger over
  time; no permanent vehicle-to-charger 1:1 mapping is assumed. Simultaneous passive
  ambiguity is reported rather than guessed. Active probes remain simulations.
- Add each EV site with explicit PE entry/site, zone, timezone and electrical limit.
  Configure boost threshold/target, long-trip margin and price-tie tolerance using
  existing defaults unless deliberately changed. A guest power sensor can reserve
  measured guest load; missing uncertain guest demand suppresses capacity.
- Brain and Optimizer may be enabled independently. Review command capability
  mappings if desired; they remain inert. There is **no live enable control**.
- Configure/Options permits repeatable add/edit/remove/provider replacement/reorder.
  Removal clears active session references; history remains stored. Re-adding a
  vehicle creates a new logical identity; do not expect automatic history reassignment.

Useful entities include associations/physical sessions, source timestamps/provenance,
forecast allocations/next start/finish/07:00 SoC, producer readiness, supported command
capabilities, and lifetime/day/week/month/year measured energy, known cost, unpriced
energy and distance. Forecasts are conditional simulations; unsupported/stale inputs
produce explicit unavailable/provisional status. Commands do not run from sensors.
