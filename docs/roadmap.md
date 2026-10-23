# Scope and follow-up gates

This is the first read-only developer-preview slice for Issues #1–#4. Keep those
issues open until their full acceptance requirements and deployment evidence exist.

Implemented: native scaffold, one shared logical registry, reviewed semantic device
mapping, field fallback, independent toggles, association engine and bounded passive
matching, durable simulated plug sessions, manual guest simulation, pure bounded
probe simulation, centralized simulation guards, official Nord Pool response reader,
explicit tariffs, preserved staged planner and 07:00 forecast sensors, multi-site
state, measured guest-budget subtraction, diagnostics, tests and CI metadata.

Next work before calling the product complete:

- Brand capability adapters validated against actual Tesla Custom/Fleet registry
  metadata and other vehicle/charger integrations; stronger upstream freshness and
  cross-field snapshot reconciliation; registry replacement/rename handling.
- Provider device replacement/reordering UX and entity registry rename handling.
  Current UI edits vehicle/site/charger settings and linked provider fields in place.
- Native measured energy/cost/distance entities and optional odometer mapping using
  the retained, tested history engine; richer tariff calendars/fees and currencies
  beyond explicit DKK input, plus overlapping-site membership configuration.
- Durable real physical-session continuity across HA downtime. Current conservative
  reconfirmation prevents stale authority; no claim of uninterrupted guest control.
- A live executor is excluded. Production command ownership, capability-specific
  validation, acknowledgments, uncertain outcomes, budget storage and commissioned
  automatic physical probes need separate reviewed work and owner-supervised tests.
- Broader parity fixtures for every Cheap Boost transition, guest/restart race,
  source mismatch and load-sharing scenario; real HA OS/Raspberry Pi observation.
- Full remote HACS validation and repository metadata checks once API networking is
  available. A local schema pass is not HACS catalog acceptance.

No stable release, merge, deployment or production switch-over is part of this PR.
