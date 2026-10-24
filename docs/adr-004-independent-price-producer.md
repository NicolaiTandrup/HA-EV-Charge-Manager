# ADR 004 — Independent authoritative Price Engine

Owner decision, 2026-10-24: HA-Energy-Price-Engine owns Fetch → Normalize → Calculate
→ Persist → Lookup, source scheduling and pricing UI. EV Charge Manager consumes
only final, verified, VAT-inclusive DKK/kWh through proposed contract v1. It owns
vehicle/session management, simulations, planning and measured EV history.

New sites use explicit producer config-entry/site mapping. Missing producer is a
readiness limitation, not a reason to duplicate calculations or fall back silently.
The producer repo has requirements but no implementation yet. Consumer contract
regressions use a mock read-only service; runtime interoperability remains unproven.

Existing pricing modules, dated fixtures and PRs #11/#12 remain tested migration and
reference material. Legacy sites are neither rewritten nor switched automatically.
New pricing/tariff work belongs in the independent repository; no permanent price
subsystem growth in EV Manager. Optional revision events only invalidate consumed
ranges and do not change charging ownership or issue commands.

Producer issue #4 records invoice-backed household EWII markup 0.030 DKK/kWh ex VAT
for June–September 2026. This scoped historical fact supersedes the earlier question
for those months only. Raw invoices are absent from this workspace: no raw-file
verification or personally identifying invoice fixture is claimed. There is no
current-contract inference and no propagation to other sites. Invoice comparison
and supplier UI belong to the producer.
