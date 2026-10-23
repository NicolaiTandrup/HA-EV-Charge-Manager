# Scheduled price refresh and recovery

The price engine's own timer uses Europe/Copenhagen civil time, independent of
HA's global timezone. It schedules the next absolute UTC trigger and rearms after
completion; daylight-saving days use local midnight boundaries, not 24 UTC hours.
Entry unload cancels timers, including a refresh already finishing during unload.

| Local time | Requested day | Rule |
| --- | --- | --- |
| 13:05 | Next day | Always verify publication; availability is not guaranteed |
| 13:20 | Next day | Retry only if durable table incomplete or unverified |
| 13:40 | Next day | Same conditional retry |
| 23:59 | Next day | Conditional rescue |
| 00:01 | Current day | Always sync sources, even after successful publication |

Startup loads durable records first, then verifies current/next-day inputs. It
backfills missing days and does not recalculate unchanged signatures. Operational
status is kept separately from the price table: READY, INCOMPLETE, STALE or ERROR,
requested local date, expected/valid slot counts, last attempt/success and reason.
A complete old table alone does not certify an incomplete new source publication.
Official day publications must cover a complete, contiguous UTC local-day range
before replacing that day's records. A failed/partial correction retains old
verified prices intact, records the failure/incompleteness, and permits bounded
retries. Missing data is never zero-cost power.

Only a changed final future table requests a scheduler-triggered replan. Unchanged
00:01 verification causes no price writes. The existing vehicle/session freshness
watchdog remains independent and cannot issue physical commands; safety/freshness
changes may still reevaluate its forecasts. This read-only preview never stops an
active vehicle when publication fails; the original production Node-RED controller
remains responsible for actual charging. Native forecast/status entities show
missing/stale inputs and conditional planning assumptions.

Missed scheduled events while HA is stopped are reconciled by startup verification;
no requirement to replay every missed job. Source changes can also refresh prices
between scheduled events without waiting for a dashboard/optimizer read.
