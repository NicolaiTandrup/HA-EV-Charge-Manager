> Pricing ownership update (2026-10-24): ADR 004 makes the independent
> HA-Energy-Price-Engine authoritative. Pricing-producer details below document
> preserved migration/reference work; new EV sites use the versioned consumer.

# ADR 001 — Unified native read-only integration

Status: implemented for developer review. Issues #1–#4 are the requirements,
not a claim that all future control capabilities have shipped.

## Identity, configuration and lifecycle

One config entry owns a shared vehicle registry and command infrastructure.
Vehicle UUIDs survive name changes and provider ordering. HA device IDs identify
provider devices, not physical vehicles. Multiple devices can feed one logical
vehicle; one device cannot feed two logical vehicles. Removing/recreating a
vehicle intentionally creates a new identity. Deployed core has no Tesla names,
VIN matching, vehicle SDK or vendor-specific network dependency.

Brain is one global association engine so identities cannot be assigned twice.
Optimizer uses one independent planner state/history namespace per site. Neither
module owns physical commands. A single event/watchdog coordinator serializes
snapshots; HA owns configuration, own-state storage and sensors. Options reload
unloads sensor/event subscriptions and flushes storage. Only configured entities
are read; explicit unknown/stale values suppress availability.

The engine's unique graph search is bounded to eight pending chargers and never
uses iteration order, historical identity, default-car preference or guesses.
Multiple valid matchings remain ambiguous. Probe simulations require separate
vehicle and charger commissioning and never feed their synthetic result back
into the live association engine.

## Read and authorization boundaries

Each logical vehicle has ordered providers and per-field mappings. A fresh valid
primary off/zero wins over any fallback on/nonzero. Invalid/nonfinite/out-of-range
values fall back; no fallback network request is issued. Returned fields include
provider, source entity and HA report timestamp. A fresh HA report may still
contain upstream cached values; provider freshness must be verified in device trials.
No guarantee is made that independently reported fields form one atomic snapshot.
The forecast guard requires its selected input reports to lie within a configurable
window (120 seconds by default), rejects missing required fields and contradictory
charging-on/cable-off observations, and exposes machine-readable health reasons.
Only active charging power participates; retained idle power/odometer reports do
not. Provider precedence is unchanged. The same health gate applies to Optimizer
simulation intents using a fresh read; Brain-only simulation does not require
Optimizer fields. Connection contradictions block all known-car simulation intents.
This conservative HA-side check neither proves upstream freshness nor terminates
an established Brain physical session.

Known associations qualify for simulated managed sessions automatically. Unknown
session authorization is explicit and session-scoped; it does not assign a vehicle.
Zero demand, completed charging and unavailable status do not revoke a physical
session. Recognized physical disconnect does. Unknown status suppresses current
availability and reserves identity. Stored sessions retain IDs but lose simulated
authority on first connected observation after restart: a missed unplug cannot be
proven absent. Persistent authorization across outages requires a charger-provided
monotonic physical-session identifier before any live implementation.

All public command intents pass one simulated ownership/idempotency/budget boundary.
A separate dormant injected-transport executor is mock-tested; see
[executor acceptance boundary](command-executor.md). It is not wired into the
integration and has no default transport.
Guest sessions only admit manual ownership. There is no transport, retry loop,
production flag, vehicle API or charger service dispatch. Command estimates are
not billing data; external Fleet polling remains outside our ownership.

## Independent module operation

Brain off: planner uses the shared vehicle registry's fresh cable + exact tracker
site membership. It does not fabricate charger identity. Optimizer off: Brain and
session observation remain usable. Both off: configuration/status still work.
When Brain is enabled the planner admits fresh uniquely associated vehicles only.
Guest session simulation authority excludes that session from managed plans.
Measured guest load may reduce the available charging budget without authorizing
an optimizer stop or probe. Separate configured sites have unique zone states;
overlapping site membership needs an explicit richer site capability model later.

## Price and forecast ownership

Use official HA Nord Pool response services, never private integration internals.
That read-only HA service is explicitly permitted; no vehicle/charger services are.
Nord Pool rows are DKK/MWh; planner inputs are all-in DKK/kWh. Explicit price basis,
fixed charges, optional timestamped grid charges and VAT prevent accidental
addition to an already-inclusive source. Missing prices/tariffs and stale guest
measurements cannot create a complete forecast.

Keep the original pure planner and measured history engine. Do not label scheduled
energy as actual energy. Storage preserves planner deadlines so restarts cannot
slide long-trip/low-SoC anchors. Published history entities and optional odometer
mapping remain a follow-up even though the engine and tests are retained.

## Rollout and compatibility

Original exports stay byte-identical in node-red/. No production service is
connected during development. HA OS/Raspberry Pi compatibility follows native async
HA APIs and dependency-free deployed modules, but requires a hardware trial.
Honeycomb is an optional consumer of schema-versioned entities; no foreign repo,
issue or UI contract is changed as part of this work.

Before real control: owner review, per-vehicle AND per-charger capability
commissioning, durable device session continuity, acknowledgment/timeout handling,
uncertain outcome suppression, budget persistence, manual override and reversible
probe hazards; then owner-supervised isolated test and rollback plan. No merge,
stable tag, release, Node-RED disable or live HA automation edit is authorized here.

## Alternatives and review sequence

Two integrations plus a shared library would preserve separate installation names,
but duplicate config-entry ownership and require a cross-integration session and
command authority protocol. It also adds library release coordination on HA OS.
A single integration keeps one configuration/identity/authority boundary while
module switches serve Brain-only and Optimizer-only users. The pure engines remain
independently testable internal modules; no external shared package is needed now.

Review architecture/provenance and preserved exports first, then the stacked
integration implementation. Keep both source draft PRs and repositories intact.
The newer Manager issue #3 and owner instruction specify automatic probes after
commissioning; older Brain issue #4's per-probe approval proposal is historical.
This preview only simulates either policy; any real unattended probing remains a
separate owner-supervised safety gate, never inferred from simulation success.
