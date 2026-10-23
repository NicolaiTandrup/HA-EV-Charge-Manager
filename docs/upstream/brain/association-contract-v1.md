# Association data contract v1

The aggregate Sensor's initial suggested ID is `sensor.ev_charger_assignments`.
HA may add a suffix; users may rename it. Consumers must select the actual entity,
check availability and schema_version, and treat this entire integration as optional.
Never infer a vehicle or charger from a friendly name or an entity suffix.

State: integer number of valid current associations. Attributes:

```yaml
schema_version: 1
operating_mode: log_only
updated_at: '2026-10-23T09:00:00+00:00'
assignments:
  - charger: station_1
    car: vehicle_a
    car_name: Vehicle A
    mode: auto_assigned
    valid: true
    fresh: true
    updated_at: '2026-10-23T09:00:00+00:00'
    last_associated_vehicle: vehicle_a
chargers: []  # all charger rows, including invalid/unassigned rows
```

IDs are user-configured stable slugs scoped to this config entry; display names
are informational. Never join on car_name. `assignments` includes only valid rows;
`chargers` includes all rows and is intended for diagnostics/UX. Each vehicle and
charger appears at most once in assignments. Timestamps are timezone-aware UTC.
`updated_at` is evaluation time, not the last source report or last physical change.

Modes: disconnected, unavailable, pending_match, ambiguous, stale, auto_assigned,
manual_until_disconnect. Invalid rows have car/car_name null. Physical disconnect
removes the row from assignments during the next evaluation. An unassigned manual
row is not confirmation. `last_associated_vehicle` is history only, never a match.
It is not persisted and may reset at restart. No confirmed assignments are restored.

Fresh source reports use HA State.last_reported, with a configurable max age
(default 900 seconds). Watchdog evaluation every 15 seconds bounds expiry delay;
state changes request an update (HA coordinator debouncing may delay it).
A source integration repeatedly reporting cached values does not prove upstream
freshness. Configure an appropriate limit and validate that provider's update rate.
Freshness of an existing session requires fresh recognized charger status and a
usable fresh cable state (on or off); GPS may be unknown because it cannot end an
established physical session. New sessions additionally require cable on and an
exact fresh tracker zone state. Fallback supplies missing/stale/unknown primaries.
Unknown charger status suppresses publication and reserves previous identity;
recognized disconnect clears it. If the aggregate itself is unavailable, all rows
must be considered invalid, even if HA retains attributes.

Consumers should also reject evaluations older than their configured timeout,
including when HA is unreachable or a cached dashboard state is displayed.
Never use an old list as a physical charging instruction. The contract reports
inferred association, not charging authorization, power, SOC or vehicle identity
verified by the charger. No Honeycomb dependency is required in either direction.

Breaking field/meaning changes require a schema_version increment. Adding optional
fields is compatible. The proposal is posted to [Honeycomb NG issue #126](https://github.com/NicolaiTandrup/honeycomb-menu-ng/issues/126).
Consumer implementation and maintainer acknowledgement are still pending.
