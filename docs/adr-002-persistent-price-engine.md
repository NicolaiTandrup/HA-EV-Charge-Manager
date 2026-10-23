# ADR 002 — Persistent per-site Price Engine

Use one versioned HA Store snapshot per site, with immutable records, an in-memory
UTC index and serialized atomic batch replacement. HA Store already provides atomic
file replacement and lifecycle integration; SQLite would add connection/schema
management before measured accounting justifies it. Default retention is 365 days
per site (approximately 35,000 quarters); historical export/accounting beyond that
window requires separate archival. Deployment adds no dependencies.

Fetch/normalize/calculation happens at source-update/startup/scheduled boundaries.
Optimizer and sensors read precomputed stored final DKK/kWh amounts only. Source
signatures exclude verification-only timestamps so unchanged checks cause no price
calculation/write. Memory is replaced only after a durable save succeeds. Reads
return immutable records and indexed ranges; the planner receives a bounded window.

Records preserve UTC start/end, site, currency/unit, final inclusive amount, explicit
component/VAT conventions, source audit metadata, calculation time and revision.
External all-in feeds preserve their declared inclusive total without reverse-
engineering VAT. Spot-mode fees are configured explicitly excluding VAT. A later
adapter may introduce separately dated components without changing the reader API.
Subscriptions remain separate from marginal price ranking.

Already-started intervals retain their original final amount/components/provenance.
Verified corrections change future intervals only; unchanged records retain their
revision. Historical revisions are not silently rewritten. Missing slots remain
missing, never zero-filled. Duplicate/overlapping/off-quarter records are rejected
before writing. Local-day completeness uses timezone-aware civil midnights (92,
96 or 100 UTC quarters on Danish DST transition/normal days).

Source failure keeps last durable verified records and publishes an error/stale
state. A sensor read cannot cause fetch or recalculation. An engine-owned sensor
cannot be configured as its own upstream source. Startup loads before refreshing;
future scheduler work adds publication retries/catch-up around this same boundary.

HA Store rewrites a site's snapshot atomically for a changed batch; this is not an
append-only billing ledger. Only changed future record values/revisions are
replaced in that snapshot. Retention/pruning happens on updates, not on reads.
