# Measured EV history and attribution

Native sensors expose per-site/per-logical-vehicle observed charging energy,
**priced** charging cost and unpriced measured energy. One global distance ledger
belongs to each logical vehicle, so visiting multiple sites cannot duplicate its
odometer distance. No vehicle, charger, automation or supplier account is written.

Energy integrates consecutive actual power reports with the existing trapezoidal
method, explicit W/kW normalization, physical/site/guest eligibility and a 180-second
maximum source-report gap. Repeated watchdog reads are not new measurements.
Invalid readings, source changes, disconnects and restarts break the baseline;
there is no downtime extrapolation. SoC/target/forecast availability is not required
for a fresh, independently attributable physical power observation.

These are power-derived observation estimates, not a certified energy meter or
invoice reconciliation. Verify that the configured power source represents AC input
before interpreting amounts as delivered electricity cost; otherwise they describe
that selected measurement boundary. Intervals without valid telemetry are not
estimated. Price coverage describes **recorded energy**, not all possible charging.

Missing/incomplete price coverage still records measured energy but increments
`unpriced_energy_kwh`; it is never assigned a zero price. The cost entity reports
known priced cost with `cost_coverage: partial`. Negative final prices legitimately
reduce accumulated cost, hence monetary TOTAL rather than TOTAL_INCREASING.
Fixed subscriptions and household invoice allocations are producer concerns.
Backfilling unpriced intervals requires a future explicit settled-history contract;
this preview does not guess, retroactively apply a current tariff, or invent costs.

Distance uses explicit km/mi observations and stable registry/provider identities.
A rename preserves continuity; provider replacement/calibration changes rebase,
never count the jump as travel. Nonfinite values, resets and outliers are guarded.
Durable totals survive reload while transient measurement baselines do not.

With Brain enabled, the physical charger session determines the eligible site.
A GPS change cannot move a reserved session to another site's prices; missing or
contradictory planning inputs suppress its forecast without ending the session.
Unknown/manual guests remain excluded from Optimizer ownership/measurement
attribution to a configured car. Brain-only behavior stays independent of prices.

## Calendar entities

Each measured total also has day/week/month/year entities. Calendar buckets are
persisted alongside lifetime totals. Site energy/cost uses the site's timezone;
global distance uses HA's timezone. The ledger retains the timezone chosen when
its first dated measurements are recorded so later UI timezone edits do not relabel
past records. Review/rekey explicitly before changing that accounting boundary.
Weeks start Monday; months/years use local civil boundaries, including DST.

Power intervals are split exactly at local midnight and price boundaries using
the same trapezoidal measurement. A partially unpriced sample remains entirely
unpriced, conservatively matching lifetime coverage. Negative costs remain credits.
Distance increments are attributed to the day of the observed odometer report;
travel time across a gap is unknown and is not redistributed to invented dates.

Legacy lifetime totals have no recoverable dates and are never assigned to current
calendar buckets. Period sensors report only recorded buckets, expose their first
recorded date and use explicit calendar resets. They cannot reconstruct missing
telemetry or establish billing completeness. No retention pruning or settled-cost
rewrites are introduced; day buckets survive reload/restart. More detailed session
exports and historical settled-price backfill remain follow-ups.

## Observed session segments and charger reports

Session/charger accounting attributes the exact deltas already calculated by the
vehicle/site history path. It does not integrate power twice or consume plans as
measurements. Each segment records logical charger/vehicle/site, physical HA-session
token and device reference, observation/sample times, meter coverage, known cost,
unpriced energy, daily deltas and the final price evidence actually used. Costs
and finished segments are never repriced by later PE revisions.

A replug, association/site/device boundary or restart closes an observation segment
without asserting physical continuity. Restart closure uses the last observation,
not invented charging during downtime; a continued HA session token is not proof
of one uninterrupted physical plug. Cached pre-start power reports cannot become
a baseline for post-start integration. Unknown status preserves the active physical
reservation; recognized connection boundaries close it. Removing configuration
retains historical segments and marks that administrative boundary explicitly.

This is a **vehicle-power trapezoid estimate**, not a certified charger AC meter.
A guest or missing meter has no measured intervals, so its energy/cost entities
are unavailable rather than fabricated zero. Known unpriced energy remains explicit.
Intervals outside the existing 180-second gap/source/skew guards are not invented.
Calendar deltas follow the underlying site's pinned accounting timezone; segment
day/week/month/year reports aggregate those recorded site-clock buckets.

Each charger has fixed active-segment and lifetime counters; no HA entity is
created per historic session. Detailed charger and vehicle/site period reports
are optional entities disabled by default for new installs. Charger period reports
are bucket views rather than monotonic long-term-statistics counters; lifetime
entities remain the cumulative statistics source. Missing intervals and unmeasured
segments mean recorded totals cannot claim full billing coverage.

Storage reuses disk-verified HA atomic writes and cancellation-safe completion.
Corrupt/unreadable accounting is preserved and reported unavailable; it is not
silently replaced with empty history. The journal/actual-control authority remains
separate and disabled. Native diagnostics expose sanitized accounting errors/counts;
native charger attributes expose a copied current-segment snapshot.
