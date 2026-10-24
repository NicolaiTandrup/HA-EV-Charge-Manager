# Development handoff

Updated 2026-10-24. Read AGENTS.md, current issues/PRs and Git state first.

## Architecture / current branch

Owner decision: **HA-Energy-Price-Engine is authoritative**. EV consumes final prices;
embedded pricing is frozen migration/reference. No further tariff/source/VAT/price
ledger/scheduling business development belongs here. See ADR 004 and shared draft
contract v1. Do not repeat the previous pricing implementation or invoice question.

Active branch `feat/authoritative-price-consumer`, based on `feat/verified-danish-pricing`
checkpoint `9d949c6`. Existing draft stack #5 → #6 → #11 → #12 stays unmerged.
New consumer draft should target #12's branch. Producer contract proposal is
[HA-Energy-Price-Engine PR #6](https://github.com/NicolaiTandrup/HA-Energy-Price-Engine/pull/6),
commit `76fa1ab`, branch `docs/ev-consumer-contract-v1` based on its main.

## Completed and validated

- Previous registry/provider, priorities, guest/simulation and pricing reference
  implementation: 138 tests and exact-head remote tests/hassfest/HACS passed.
- Current consumer checkpoint: **152 local tests passed, zero skipped**; Ruff and
  formatting passed. Official local hassfest passed before the final fixture-only
  test addition (no metadata change). Remote consumer CI must be checked after push.
- New sites explicitly select producer config entry/site through native UI. Legacy
  entries remain unchanged, visibly labeled migration/reference; no silent cutover.
- Consumer validates version, identity, DKK/kWh/inclusive VAT, revision, source age,
  sorted unique quarter ranges and READY completeness. Partial data is never zero-
  filled; stale/error/unloaded producers fail closed immediately. Matching revision
  events are filtered/coalesced; lookups throttle normally to once per minute.
- No embedded fetch, tariff arithmetic or publication timer starts for a consumer
  site. Tests spy on embedded paths and use mock read-only producer responses.
- Producer contract text/example are identical in both repos; synthetic response
  is exercised through EV decoder. Producer docs-only PR does not implement API.

## In progress / next independent task

Publish/check the separate consumer draft PR, then measured EV energy/cost/distance
history. Reuse existing History and coordinator stores; expose native sensors.
Track measured energy even when prices are missing, mark unpriced energy explicitly
and never count it as free. Keep restart baselines/gap guards, negative-cost support,
physical/site/guest eligibility and odometer provider-switch rebasing. Distance is
one logical-vehicle ledger, not duplicated across every site.

Then broaden Brain/provider safety and optimizer parity regression coverage without
changing priority order, 30-minute replanning, earliest-slot tolerance, guest guards,
command ownership or simulation-only boundary.

## Genuine external prerequisites

Independent producer currently has README/LICENSE, requirements Issues #1–#5 and
contract proposal only: **no runtime get_prices service exists**. Actual two-runtime
interoperability remains blocked pending producer implementation/adoption. Consumer
mock tests are not evidence that real producer calls work.

Producer Issue #4 records invoice-backed household EWII **0.030 DKK/kWh ex VAT in
June–September 2026 only**. Raw invoices are absent from workspace/source checkouts;
no raw-file verification, private invoice fixture, current-term inference or other-
site default is claimed. Invoice/source verification belongs to the producer.

## Validation commands

From `/workspace/HA-EV-Charge-Manager`, existing Python 3.14.8 / HA 2026.10.2:

```sh
git status --short --branch
git log -6 --oneline
/workspace/ev-manager-venv/bin/python -m pytest
/workspace/ev-manager-venv/bin/python -m pytest tests/test_price_consumer.py tests/test_history.py
/workspace/ev-manager-venv/bin/ruff check custom_components tests
/workspace/ev-manager-venv/bin/ruff format --check custom_components tests
docker run --rm -v /workspace/HA-EV-Charge-Manager:/github/workspace ghcr.io/home-assistant/hassfest
git diff --check
```

Node.js 24 required for five original Node-RED parity cases (no skips). Remote HACS
is authoritative; local full action container DNS limitation is known. Do not redo
working setup/network troubleshooting. Producer docs-only example is validated with
`python -m json.tool docs/contracts/example-response-v1.json`; no producer runtime,
hassfest/HACS or real invoice tests exist/are claimed there.

## Checkpoint / safety

Update this same file with actual results and exact validated code hashes, commit,
push and comment at meaningful milestones. Check remote CI for the exact head.
No merge, stable release, deploy or production cutover. Original Node-RED remains
byte-identical; no live HA/vehicle/charger commands. Consumer reads only proposed
producer lookup; pricing reference tests mock sources. Future real commissioning
remains per vehicle AND charger. Do not commit secrets or raw private invoices.
