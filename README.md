# EV Charge Manager

A unified, modular native Home Assistant custom integration, domain
`ev_charge_manager`. **Read-only developer preview, not a production controller.**
Existing Node-RED flows remain the current production baseline. Installing this
integration never disables or modifies those flows, helpers or HA automations.
There is no vehicle/charger command transport and no Fleet SDK or direct API client.

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
   Choose either an official Nord Pool config entry or an existing timestamped
   price sensor. Configure the complete tariff explicitly (see below).
5. Add chargers using their actual physical connection/status sensor and device.
   The legacy Garage switch mapping is unverified and is never imported.
6. Save. Configure options to edit items/provider fields or change module settings. Source
   mappings are snapshots of registry choices, not automatic reassignment when
   devices/entities change. Review mappings after replacing a source device.

Observe fresh input sources before trusting a forecast. `last_reported` means HA
received a state, not that an upstream integration fetched fresh vehicle data.
The integration never calls `update_entity`, wakes a car or requests Fleet data.
Independent Fleet integration polling is outside its control.

## Prices and forecasts

Official HA Nord Pool `get_prices_for_date` is the only external read service used.
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
