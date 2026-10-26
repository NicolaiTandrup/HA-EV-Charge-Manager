# Dormant command executor and acceptance boundary

The integration continues to expose simulations only. `CommandExecutor` has
**no transport by default**. Startup now creates the disabled journal-backed
executor for recovery diagnostics; public simulation services never call dispatch. No UI switch grants live control. Tests alone inject
an in-memory mocked HA service registry or AsyncMock. Future transport wiring,
durable commissioning, ownership handover and physical acceptance require review
and explicit owner authorization; none is implied by this module.

Known routes are taken from the preserved Brain/Optimizer Node-RED exports:
`switch.turn_on`, `switch.turn_off`, `number.set_value`. Other vendor RPCs, wakeups,
notifications and helper automations are not imported into the executor. Semantic
registry translation keys suggest capabilities only when unambiguous. Native
Configure → Review command capability mappings allows correction of individual
switch/number targets and stores stable entity-registry IDs. Device re-creation or
ownership changes fail closed; entity renames retain identity. Provider device
replacement clears command mappings. Tesla Custom, Fleet and Easee capabilities
still need real installed-version verification; unsupported RPCs are never guessed.
Current operations additionally require explicit amps and numeric min/max/step.

WRITE policy selects a supported provider before dispatch; fallback is never a
retry strategy. A per-device lock, session/owner claim, idempotency key, request
budget and unresolved-command latch prevent competing or duplicate writes. Caller
must supply fresh, authorized physical-session context and separate vehicle/charger
commissioning. Guests require manual ownership; provider preference grants no
permission. State and registry ownership are checked again immediately before a
write. Already matching state produces no write. Invalid values, unknown states,
stale reports or missing services are rejected.

A returned HA service call is `awaiting_observation`, not success. Timeout, HA error
or connection failure is `uncertain`; neither another key nor another provider is
sent while the physical device has an unresolved command. Only a newer matching
entity report reconciles the original key. `observed` means that mapped entity's
state was seen, **not** that energy flowed or a vehicle reached its SoC. Audit traces
are bounded to 50 entries; request count/budget include every attempted dispatch.
No automatic retry or wakeup is justified after an ambiguous outcome. Discovery
can be retried without sending. An unresolved command across a physical unplug or
restart needs reviewed recovery and durable device/session identifiers before live
commissioning; the dormant preview deliberately provides no override service.

The transport and commissioning flags are developer interfaces, not security proof
of real HA ownership. Real control must bind them to durable per-device authority,
exclude Node-RED writers, persist uncertain requests and reconcile actual upstream
acknowledgments. Passing these tests is not authorization to wire a transport.

## Durable journal and recovery (2026-10-25)

Native startup now loads one HA-owned command journal per CM config entry, with no
transport enabled. Reservations (intent, registry target, session/owner, request
count and uncertain outcome) are atomically saved and read back from disk before
an injected test transport is called. HA Store can swallow write errors; the
journal verifies actual disk content rather than trusting its return or cache.
Unreadable/corrupt/unsupported journals inhibit execution without overwriting them.

After restart unresolved requests reserve their physical device and require
explicit reconciliation; no key, alternate provider or different session can
automatically replay them. Read-only reconciliation requires separately verified
physical-session continuity and a fresh matching entity report after journal load,
plus current registry/session/commissioning guards. A cached startup state alone
is insufficient. There is no public reconcile/clear-uncertainty service.

Counts, unresolved/recovery state and sanitized storage errors appear in native
status/diagnostics. Request estimates persist across restart (not a billing/API
provider meter); independent integration polling is outside CM's accounting.
Completed idempotency records and ownership survive; no unsafe pruning is added.
Tests use actual atomic HA file writes, crash/cancellation windows, failed prepare
and result writes, malformed JSON, restart with disabled transport and newer-state
reconciliation. This removes in-memory-only recovery; physical continuity evidence
and future live commissioning wiring still require installed-device acceptance.

### Optimistic reports never release durable uncertainty

The native durable executor does not clear a live or recovered request merely
because HA reports the requested switch/number state. Easee and other providers
may echo setters optimistically. Explicit reconciliation now requires both verified
physical-session continuity and an independent acknowledgment attestation, followed
by the existing newer-report/registry/session/freshness checks. These internal
test inputs are never populated automatically or exposed as UI authority. Without
them, duplicate/new-key/provider-fallback dispatch stays blocked. The lower-level
in-memory executor remains a mock harness; native use is journal-backed.

## Independent devices and cancellation-safe persistence

Native execution serializes each physical device, not all network waits globally.
Different devices may have independent outstanding mock transports, but each
reservation is atomically saved/verified before its own dispatch. Journal writes
remain serialized. A cancellation while a Store executor-thread write is running
waits for that write to finish/verify before releasing the persistence lock, so
an older write cannot race past a newer reservation. Cancelled preparation never
dispatches, and its conservative reserved state is not blindly retried.

Read-only reconciliation now uses an observation-only executor path without
temporarily changing a shared transport; it cannot enable or disrupt another
device's dispatch. A journal failure blocks subsequent dispatch checks even if
another task was waiting. Per-device pending/owner/budget and independent
acknowledgment requirements remain unchanged.

Per-reserved-intent audit captures uncertain preparation, returned/failed dispatch
and verified observation states with journal-capture timestamps. Duplicate calls
do not manufacture repeated events. Older v1 journals without this additive audit
remain readable; original snapshot/attempt timestamps are retained rather than
inventing missing transition times. Sanitized last command error and event counts
are exposed in diagnostics; these reports are not evidence of physical actuation.
