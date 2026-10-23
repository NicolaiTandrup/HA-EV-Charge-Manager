# ADR 001: Native read-only EV Charger Brain

Status: accepted for implementation; production control explicitly excluded.

## Naming

Keep the repository `HA-EV-Charger-Brain` and display name **EV Charger Brain**
for continuity. Domain: `ev_charger_brain`. Alternatives: **EV Charge Link** and
**Charger Association**. Do not rename the repository without owner approval.
Suggested description: “Local, read-only vehicle-to-charger association for Home Assistant.”
The domain is repository-specific; global name uniqueness has not been registered.

## Complete reference audit

The unchanged 21-node `node-red/EV-Charger-Brain-v1.0.json` includes:

* A tab and three explanatory comments describing draft/log-only operation,
  version history, Tesla Custom primary sources and Fleet fallback sources.
* A 15-second inject (initial delay two seconds), function building an explicit
  poll list, dynamic HA current-state reads, a four-second watchdog delay and
  the central state-machine function. Config is duplicated in both functions.
* A Production gate and service router for switch on/off and boolean off,
  three service nodes with explicit action names, skipped-service debug,
  append-only semicolon CSV output, CSV debug, mobile notification and state
  debug; one HA connection config and module config (websocket nodes 0.81.0).
* Two named vehicles, two enabled home chargers, two disabled second-site
  chargers, zones, default vehicle preferences and household-specific helpers.
  Enabled/status/override IDs are derived from switch suffixes. The Garage
  switch mapping is known wrong: `switch.garage_is_enabled` must never be reused
  as a verified mapping. The owner reports `switch.garage_charger_enabled` and
  `sensor.garage_status`; these must still be verified against the device.
* Physical status normalizes underscores/hyphens and whitespace. Connected:
  ready to charge, awaiting start, charging, completed/complete. Disconnected:
  car disconnected/disconnected. Unknown/unavailable do not end sessions.
* Session state includes assigned and last assigned car, connection/disconnection
  times, pending timeout flags, last action and modes. Cable on is primary
  evidence, including a 180-second recent-on window. Both providers are queried;
  the implementation actually ORs their cable states and zone matches, despite
  primary/fallback naming. A valid primary off can therefore conflict with Fleet.
* Matching excludes vehicles assigned elsewhere; cable + zone yields assignment.
  Multiple candidates use configured default-car tiebreaker, otherwise ambiguous.
  No candidate becomes pending; watchdog marks unassigned after 600 seconds.
* Replug within 7200 seconds can reuse last identity if in zone or primary tracker
  is unknown/unavailable, without fresh cable confirmation. That branch does not
  run the same global candidate uniqueness check. Historical identity must not
  be published as new confirmation in the native contract.
* Manual helper sets manual mode and enables the charger. Helper off leaves
  manual mode in the reference. Disconnect clears current assignment, preserves
  history, disables the charger, and clears helper. Watchdog repeats cleanup.
* GPS changes for an assigned vehicle are logged and ignored while physically
  connected, including unknown/not_home; they never command session termination.
* Disabled calculates and logs SKIP actions; Log only calculates WOULD actions;
  Production emits services. Notification is gated except optional log-only
  notifications. Charging sensors are observational logs, not match evidence.
  CSV contains identity, site, mode, event, action and reason; debug publishes state.
* Internal poll timestamps reflect successful reads, not upstream freshness.
  Initial reads populate caches without change handlers; watchdog reconstructs
  some state. The export offers no durable restore/freshness contract, global
  conflict resolution, device validation, unload model or vendor-neutral UI.

## Decision

Use an async native HA config-entry integration, with a pure Python association
engine, an event-driven coordinator and a 15-second freshness watchdog. Native
entities expose results; the HA UI collects explicit device/entity mappings.
No network API, vehicle SDK, Node-RED runtime or physical service calls are used.
An ordinary custom integration can be installed through HACS after validation.

A Node-RED subflow would ease existing flow reuse but retain runtime dependency,
weak identity handling and household configuration. An App would isolate runtime
but require HA authentication and an external lifecycle. Neither is preferable
for a local association helper observing existing HA entities.

## Safety and deliberate first-phase differences

Preserve physical disconnect authority, stable active-session identity despite
unknown GPS, unique vehicle ownership and disconnect cleanup. Manual override
latches an existing identity or stays unassigned until physical disconnect;
it cannot invent a vehicle. This is an observation mode, not a manual charging
button. Because helpers are read-only, an on helper seen at disconnect is ignored
until an off/on cycle. A helper toggled off while connected does not clear the latch.

Prefer a usable primary source; fallback is used only for missing, stale or
unknown primary. A fresh primary off wins over fallback on. This deliberately
fixes the export's OR semantics. Both ends of a candidate graph must be unique;
no default tiebreaker or iteration-order assignment is allowed. Unresolved graph
components stay ambiguous, even if more complex matching might find a solution.

Replug must obtain fresh cable + zone evidence; last identity is diagnostic only.
The two-hour historical shortcut, 180-second cable grace, pending timeout,
CSV export, notifications, charging-state logging, Disabled/Production controls
and physical cleanup commands are deferred. Log-only is the sole operating mode.
Existing assignments survive cable off while charger remains connected, but
missing/stale cable or charger data suppress current publication. Sessions stay
reserved internally until explicit physical disconnect.

After restart, reconstruct only from current fresh signals; do not restore a
confirmed identity from disk. Unknown location or ambiguity can require waiting
for source updates. A manual latch whose helper has since gone off is not durable
across restart. This limitation must be resolved before production control.

## Consequences

No physical control parity is claimed. This is an independently usable read-only
first phase, exposing association to any consumer. A future control phase needs
separate approval, real device validation, durable session design and dedicated
hazard tests. Honeycomb coordination is a separate publication task; schema v1
is a proposal until its maintainers acknowledge it in issue #126.
