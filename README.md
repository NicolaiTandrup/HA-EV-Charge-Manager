# EV Charge Manager

**HACS distribution is currently blocked:** main lacks the integration. A source
ZIP/CI artifact is a manual test package, not a completed HACS beta. See
[distribution gate](docs/HACS_DISTRIBUTION.md); no branch-URL workaround is supported.

Proposed **v0.1.0-beta.1**: read-only candidate archive and CI artifact; no release
or production control is enabled. Build/install steps are in
[beta installation](docs/beta-installation.md).

**Architecture update (2026-10-24):** [HA-Energy-Price-Engine](https://github.com/NicolaiTandrup/HA-Energy-Price-Engine)
is the authoritative price producer. New sites select its config entry and site;
EV consumes verified final prices through the [producer-owned API v1](docs/contracts/price-consumer-v1.md).
Producer draft #7 implements that API; tests exercise its pinned ledger/API with
synthetic inputs, alongside mocked failure cases. Hardware acceptance remains unrun.
Missing/stale producer data fails closed. Existing embedded pricing described below
is retained as **frozen migration/reference code**, with no automatic cutover.
See [ADR 004](docs/adr-004-independent-price-producer.md).


A unified, modular native Home Assistant custom integration, domain
`ev_charge_manager`. **Read-only developer preview, not a production controller.**
Existing Node-RED flows remain the current production baseline. Installing this
integration never disables or modifies those flows, helpers or HA automations.
There is no active vehicle/charger transport or Fleet SDK. The dormant
[mock-tested command executor](docs/command-executor.md) has no default transport
and is not wired to startup or public services.

Native [provider policies](docs/provider-policies.md) support independent READ/WRITE
preferences, fallback switches and capability overrides. All controls stay disabled.

See [candidate installation](docs/beta-installation.md) and
[owner-supervised migration/rollback](docs/beta-cutover.md) for beta gates.

## Four components

- **Vehicle Manager:** one stable logical identity per physical vehicle, linked to
  multiple HA provider devices. Reviewed semantic device/entity discovery and
  explicit mappings; fresh, valid values fall back independently per field.
- **Charger Brain:** reuses the conservative association engine, adds bounded unique
  graph resolution, and exposes physical plug sessions. Unknown guest authority
  and active ambiguity probes are **simulations only**.
- **Charge Optimizer:** reuses the proven staged planner, rule persistence, measured
  history engine and Node-RED parity tests. Independent sites, 15-minute intervals,
  cheapest noncontiguous windows, low-SoC stages, long-trip rules, Cheap Boost
  simulation and site-local 07:00 SoC forecasts.
- **Command Manager:** simulation-only ownership, freshness/session validation,
  idempotency, guest protection and request estimates. No live mode exists.

Brain and Optimizer can be enabled independently. They share the same logical
vehicle registry. Honeycomb and other dashboards are optional consumers.

## Install for isolated observation

Requires Home Assistant **2026.10.2 or later**. The deployed integration has no pip
requirements or architecture-specific binaries. Tests use Python 3.14.8 and HA
2026.10.2; HA OS/Raspberry Pi hardware validation remains outstanding.

Copy `custom_components/ev_charge_manager` into HA's `config/custom_components/`
and restart HA. Alternatively, after reviewing this branch, add this repository
as a HACS custom integration repository; HACS catalog acceptance is not claimed.
Do not install development code into the live controller without owner review.

Add **EV Charge Manager** under Settings → Devices & services:

1. Choose module toggles. The integration remains read-only with either setting.
2. Add each physical vehicle once (usable battery capacity, AC power, efficiency).
3. Attach its HA provider device(s). Add Tesla Custom as preferred and Fleet as
   fallback, or use a generic integration. Review discovered fields and explicitly
   select missing/ambiguous fields. No friendly-name or entity-suffix guessing.
   A provider device cannot belong to two logical vehicles.
4. Add independent sites with exact tracker zone states and local timezones.
   For new sites choose the independent Price Engine entry/site. Its pricing
   configuration belongs in that integration. Existing legacy price sites are
   preserved only for explicit migration/reference comparisons.
5. Add chargers using their actual physical connection/status sensor and device.
   The legacy Garage switch mapping is unverified and is never imported.
6. Save. Configure options to edit items/provider fields or change module settings. Source
   vehicle fields pin stable HA registry IDs. Renames follow the verified registry
   entry; changed device ownership, disabled/deleted entries or unregistered states
   fail closed. Replacing a device requires explicit reviewed remapping.

Observe fresh input sources before trusting a forecast. `last_reported` means HA
received a state, not that an upstream integration fetched fresh vehicle data.
The integration never calls `update_entity`, wakes a car or requests Fleet data.
Independent Fleet integration polling is outside its control.

Forecasts also require a consistent vehicle snapshot. Configure the maximum
report-time difference under Modules (default 120 seconds; existing entries use
that default). Required SoC, target, cable, tracker and charging reports must fall
within that window; power is included only while charging. Missing fields or
charging-on/cable-off contradictions suppress the forecast with an explicit reason.
Retained idle power and optional odometer values do not invalidate a forecast.
Vehicle sensor attributes expose `snapshot_health`, missing fields and report skew;
anonymous diagnostics count issue categories. Raw fields and provider precedence
are preserved: consistency failures do not silently replace Custom with Fleet.
This checks HA report timing, not atomic upstream vehicle data. Brain physical
sessions remain independent; tune the window to verified source cadence.


## Prices and forecasts

Official HA Nord Pool `get_prices_for_date` supplies spot data. Optional Radius C
uses the verified public DatahubPricelist tariff API; it never calls a vehicle API.
It fetches today/tomorrow for DK1/DK2 in DKK, caches hourly, converts DKK/MWh to
DKK/kWh and expands hourly data into quarters. Missing tomorrow yields provisional
forecasts rather than fabricated prices. UTC timestamps handle DST days.

Price-sensor compatibility accepts `slots` or `raw_today`/`raw_tomorrow` arrays of
`{start, end, price}` (or `value`) with explicit UTC offsets. Numeric daily arrays
are rejected. Set the multiplier explicitly: 1 for DKK/kWh, .001 for DKK/MWh.
Currency conversion is not inferred; sensor inputs must be DKK after scaling.

- `spot_ex_vat`: `(spot + grid + tax + supplier + optional grid schedule) * (1 + VAT)`.
  Components are DKK/kWh excluding VAT; VAT is a fraction, e.g. 0.25.
- `all_in`: already complete DKK/kWh. All additions and VAT must be zero; adding
  them again is rejected. Never add a grid schedule to this basis.
- Optional grid-tariff sensor: fresh timestamped `slots` in DKK/kWh excluding VAT,
  covering every planned interval. Choose either a fixed grid value or the schedule,
  or explicitly split a fixed and variable grid component to avoid double counting.
- Optional guest-demand sensor: measured W/kW subtracted from each site's configured
  charging budget. An observed unknown or offline reserved session without a demand mapping, or
  missing/invalid configured demand, makes that site's plans
  unavailable. Set the site budget after other household loads.

Sensors expose proposed schedules, expected finish/start and expected SoC at the
next site-local 07:00. Forecasts are conditional estimates, never actual charging
instructions. With Brain enabled only its fresh unique associations enter plans;
with Brain disabled fresh cable + exact site location gate the planner. Guest
simulation authority cannot be taken over by Optimizer. Separate site zone states
are required in this first UI; ambiguous overlapping sites are not auto-selected.

## Simulation services

All services require response mode; use HA Developer Tools → Actions or
`action` with `response_variable` in an **isolated test** automation.

- `ev_charge_manager.simulate_guest_authorization`: `charger`, current `session_id`
  from the assignments sensor. Changes only integration-owned simulated state.
  Physical disconnect revokes it; zero power does not. HA outages require
  reconfirmation because unplug/replug continuity cannot be proven.
- `ev_charge_manager.simulate_command`: `charger`, `session_id`, unique `key`,
  `owner` (`brain`, `optimizer`, `manual`), `action` (`start`, `stop`, `limit`, `probe`),
  optional `value`. Returns a validation result and `physical_commands: 0`.
  Guest sessions reject Brain/Optimizer ownership and probing.
- `ev_charge_manager.simulate_probe`: synthetic `samples` mapping each candidate ID
  to a power response, `candidates`, `charger`, `commissioned_vehicles`,
  `commissioned_chargers`, optional `guest`. At most two modeled pulses, each with
  a restoration trace. Its result never establishes live association.

Request counts are simulation estimates and reset on reload. They are not actual
Fleet billing or a production API guard. A live executor, acknowledgments, uncertain
command handling, real probe commissioning and migration require separate work and
explicit owner-supervised testing. Commissioning must be **per vehicle and charger**.

## Develop and validate

```sh
bash scripts/setup-cloud.sh
/workspace/ev-manager-venv/bin/python -m pytest
/workspace/ev-manager-venv/bin/ruff check custom_components tests
/workspace/ev-manager-venv/bin/ruff format --check custom_components tests
docker run --rm -v "$PWD:/github/workspace" ghcr.io/home-assistant/hassfest
```

Node.js is required for the original Node-RED planner parity tests. CI includes
Python tests, hassfest and HACS checks. See [architecture](docs/architecture.md),
[provenance](docs/provenance.md), [validation](docs/validation.md) and
[remaining work](docs/roadmap.md). No stable release or production cutover is made.

Prices are now precomputed in a per-site HA Store table (default retention 365 days).
Source updates/startup calculate; optimizer and dashboard reads only look up stored
final DKK/kWh. Already-started prices retain their accounting provenance; verified
corrections replace future records. Unknown slots remain unavailable. See
[ADR 002](docs/adr-002-persistent-price-engine.md). Scheduled publication/retry/midnight refresh is implemented; no production
price-source switch is performed. See [refresh policy](docs/price-refresh.md),
[verified source ADR](docs/adr-003-verified-danish-sources.md) and
[dated pricing configuration](docs/dated-pricing.md).

Measured EV history now exposes native site/vehicle energy, known priced cost,
unpriced measured energy and one distance ledger per logical vehicle. Values come
from new power/odometer reports, never planned allocations; see
[measurement assumptions and coverage](docs/measured-history.md). Independent
producer interoperability is still pending actual producer API implementation.

Portable native fixture previews and isolated Pi acceptance: [PAHA02-DEV guide](docs/paha02-dev.md).
