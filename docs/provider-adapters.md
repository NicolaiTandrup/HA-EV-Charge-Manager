# Source-backed provider profiles

The generic profile consumes HA registry semantics and reviewed manual mappings.
Provider classes translate only verified metadata. No SDK, vendor API fetch,
refresh, wakeup or command authorization is introduced. All suggestions still
require review; manual overrides remain registry/device-bound and editable.

- Tesla Fleet: HA 2026.10.2 entity descriptions use charge_state_* keys. Battery,
  charge limit, cable, power, charge state/current and odometer are normalized.
  Actual location is selected; the route/destination tracker is not the car's
  current position. Where a sensor enum and switch share the charging key, the
  unambiguous binary/switch state is preferred. This is a HA entity report, not
  proof of physical current.
- Tesla Custom: reviewed alandtse/tesla commit
  87010a33df0c6119c4134838dbd7253b6af5edeb uses the complete slugified VIN+type
  unique-ID contract when translation keys are absent. Anchored VIN syntax,
  provider platform, domain and device binding are required; display/entity names
  and arbitrary suffixes are never used. Actual location excludes destination.
  Source files: base.py, sensor.py, binary_sensor.py, number.py, switch.py and
  device_tracker.py. No upstream code is copied; tests use synthetic metadata.
- Easee: reviewed nordicopen/easee_hass commit
  85dbd07d6b4e4059735ecd9c97b5569fb52347d0 uses easee_status for charger status
  and is_enabled for its enabled switch. These normalize to reviewed generic
  status/enable semantics and standard HA switch routes. Source files: entity.py,
  const.py and switch.py. This provider may optimistically publish switch state
  and may log some upstream errors without raising them: a service return or
  matching switch report is not proof of actual charger authorization/energy.

Unknown versions, disabled entities, multiple equivalent candidates and missing
evidence stay unresolved for manual review; they do not silently authorize a
capability. Provider fallback is selection before dispatch only. Exact registry
VIN identity guards and stable source reconciliation remain in the shared registry.

These are source/registry fixture validations, not acceptance on the owner's
installed versions. Verify telemetry cadence, true upstream freshness, permissions,
reported units, switch semantics and physical-session continuity on target devices
under separate owner authorization. Current CM startup has no live transport.
