# Configure automatic DSO and dated all-in components

The default manual/external all-in workflow remains available. To observe Radius C
with official Nord Pool or another explicitly normalized spot source:

1. Choose spot price basis (`spot_ex_vat`, or `spot_incl_vat` only for an explicitly
   inclusive external **spot-only** feed). Official Nord Pool is ex VAT.
2. Choose `radius_c`; set fixed grid addition to zero and omit a grid schedule
   sensor to avoid duplicate DSO costs. Optional fallback is explicit DKK/kWh ex VAT.
3. Set the verified cache age policy. Stale/outage/fallback status is exposed; no
   automatic source change is made in production Node-RED.
4. Either retain manually configured ex-VAT tax/supplier additions, or opt into
   dated components. Dated mode requires legacy tax/supplier additions to be zero.

For dated mode, `dated_components` is a list of objects with:

- `id`: `energinet_net`, `energinet_system`, `electricity_tax`, `supplier`, or a
  separately identified extra charge.
- `amount`: the verified numeric amount; `unit`: `ore/kWh` or `DKK/kWh`.
- `vat_included`: explicit boolean; `vat_rate`: fraction (e.g. 0.25).
- `valid_from`, `valid_to`: ISO local dates, end exclusive.
- `source`, `verified_on`: source/contract reference and ISO verification date.
- Optional `locked: true`: preserve an intentional manual override in that period.
- Optional `eligibility: heating_above_4000`: requires explicit registered-heating
  confirmation and verified annual usage/year, never inferred from car/site data.

Enable `danish_public_rates` to add the issue-verified 2026 Energinet and 2026–2027
tax periods. You must still supply a dated **supplier contract** rule. No EWII
contract is inferred from public advertising or the historical Node-RED defaults.
For 2027 network fees and later tax periods, supply new verified dated rules.
Overlapping equally ranked versions, missing components, unknown units or ambiguous
VAT fail closed. Locked rules take precedence only within their effective period.

For subscriptions, use a distinct ID and `unit: DKK/month`. They appear under
`fixed_subscriptions_excluded` in stored components and are not added to the final
marginal per-kWh price. Other component amounts are normalized once into separate
ex-VAT, VAT and inclusive amounts, then persisted with the final total.

Use current/next/status price entities to inspect stored totals, component/source
provenance and warnings. Compare against the existing Energy Price Broker read-only;
this branch does not change `sensor.real_energy_price`, helpers, automations or
Node-RED. Actual household comparison requires owner-provided observation data.
