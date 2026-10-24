# Dormant command executor and acceptance boundary

The integration continues to expose simulations only. `CommandExecutor` has
**no transport by default**, is not created by startup, and is not called by the
public simulation services. No UI switch grants live control. Tests alone inject
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
