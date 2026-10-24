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
