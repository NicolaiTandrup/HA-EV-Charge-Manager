# EV Charge Manager development instructions

## Start every session from evidence

1. Read `docs/DEVELOPMENT_STATUS.md`, then the relevant GitHub issues and open PRs.
2. Inspect `git status --short --branch`, recent commits and the active PR head
   before modifying files. Preserve existing changes. Use this isolated checkout;
   do not create a worktree unless the owner requests one.
3. Determine what is already committed and validated. Resume the highest-priority
   unfinished task; never repeat completed work or restart the integration.
4. If the handoff is missing/stale or the previous task ended unexpectedly,
   reconstruct progress from Git history, PRs, test results and repository docs.
   Record uncertainty explicitly; a written implementation is not a validated one.

## Architecture and safety

Preserve `docs/architecture.md`, the modular native `ev_charge_manager` domain,
shared vehicle identity/command infrastructure, and independent Brain/Optimizer
toggles. Reuse the ported engines and existing tests. Maintain source provenance
and license notices. Node-RED exports remain byte-identical production baselines.

All exposed native controls are read-only observations or simulations. A dormant,
explicitly injected/mock-tested command executor may be developed, but it must have
no default live transport and no startup/public-service activation. Never issue live
vehicle/charger commands, wake vehicles, modify running HA/Node-RED automations,
or deploy production charging commands without explicit authorization. Official
Nord Pool read services are allowed; development tests mock them. Commissioning
for future real control is per vehicle **and** charger. Do not infer authorization
from simulations, a passing test, or an existing guest session.

Never merge, publish stable releases or cut over production without owner approval.
Keep draft PRs and documented acceptance gaps honest; CI success is not hardware
acceptance or HACS catalog inclusion. Never commit secrets, unreviewed production
configuration, caches or temporary debugging artifacts.

## Work and checkpoint workflow

Prefer small, coherent, tested and reviewable commits on the feature branch.
Continue autonomously while requirements are clear. Ask the owner about meaningful
design, compatibility or safety decisions. When blocked, document the exact blocker
and continue safe independent work.

At natural checkpoints, especially before stopping or approaching limits:

1. Run relevant tests when feasible; retain exact counts/results and distinguish
   local validation, remote CI, skips, failures and unrun hardware checks.
2. Update `docs/DEVELOPMENT_STATUS.md` with completed/in-progress work, active
   branch, validated commit, exact commands, prioritized remaining tasks, blockers,
   decisions and a precise next-session action.
3. Commit valid coherent changes, including the handoff. A status document cannot
   contain its own final commit hash; identify its included change by commit
   subject, and record exact validated hashes when known.
4. Post a concise progress comment on the active GitHub issue or PR when meaningful
   progress or a blocker exists. Avoid duplicate/no-progress comments.
5. Push when access permits. Check CI for the pushed head; report pending/failing
   checks rather than claiming success. If validation finishes later, update the
   handoff at the next checkpoint.

If interrupted, leave recoverable work and clear status; the next session must
reconstruct any missing checkpoint rather than blindly repeat commands.

## Authoritative pricing boundary (owner decision, 2026-10-24)

HA-Energy-Price-Engine owns price fetching, tariffs, VAT, scheduling and durable final
price records. EV Charge Manager consumes the versioned read-only contract under
`docs/contracts/`. Existing pricing modules/tests are frozen migration/reference
code, not a permanent subsystem to expand. Do not add new supplier policies or
invoice-derived defaults here. Household EWII invoices are historical evidence for
that household/period only; never infer another site's or a later contract's rate.
Preserve the existing migration path until an explicit owner-approved cutover.

## Beta migration evidence

The old Energy Price Broker uses legacy HACS Nordpool while PE uses official HA
Nord Pool. Do not require both brokers/integrations to run simultaneously. Use
recorded historical exports/offline parity and the owner-approved atomic cutover
runbook in docs/beta-cutover.md. No production cutover or prerelease is authorized.
Keep hardware acceptance, durable command authority/recovery and missing source
fixtures explicit; green CI alone does not make a live beta controller ready.
