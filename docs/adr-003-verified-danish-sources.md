# ADR 003 — Verified Radius source and dated component boundaries

## Live research (2026-10-23)

Authoritative endpoints were read without credentials:

- `https://api.energidataservice.dk/meta/dataset/DatahubPricelist`
- `https://api.energidataservice.dk/dataset/DatahubPricelist` filtered by exact GLN,
  charge type and product.
- `https://radiuselnet.dk/priser/` embeds
  `https://app.cerius-radius.dk/prices?grid=radius&private=1`.

Actual Radius C rows **are available**: owner `Radius Elnet A/S`, GLN
`5790000705689`, charge type `D03`, product `DT_C_01`, note `Nettarif C`, resolution
`PT1H`. Nine product versions were returned, including 2026 April/October changes.
Tests retain those public rows verbatim with attribution here. There are no personal
or household data in the fixture. Do not select similar names, producer tariffs,
local collective products or fixed subscriptions as domestic C energy charges.

Metadata explicitly defines Price1–24 in **DKK/kWh**, local Danish hours, and
ValidFrom/ValidTo in Danish local time. It documents the preceding-hour treatment
of the DST-affected hour. Adjacent effective periods are treated as half-open.
`VATClass` is explicitly indicative and may be erroneous: do not infer VAT from it.
The official Radius app's public bundle (`index-Dd5dsjEV.js`) displays raw hourly
prices using `1.25 * raw * 100` for its “Med moms” øre/kWh setting, confirming the
Radius preset's **raw ex-VAT** convention independently of VATClass.

Actual April 2026 ex-VAT low/high/peak: 0.106175 / 0.159262 / 0.414082 DKK/kWh.
October 2026: 0.106175 / 0.318524 / 0.955573. Rounded inclusive øre values match the
owner's 13.27/19.91/51.76 and 13.27/39.82/119.45 references. January–March 2026
still uses the prior effective version; the April rates are not backdated. The
current response's last future version ends 2027-04-21; coverage beyond a real
published boundary is unavailable, never guessed from seasons.

## Source/caching decision

Use the documented structured API, not the embedded app's implementation-specific
feed. The metadata recommends one request per GLN/product per day and says the
source is generally updated before 09:00. A shared durable cache is keyed by exact
GLN/product; successful refresh is at most once per publication-day bucket (09:00 local
boundary), with bounded extra retries when required effective coverage is missing.
A midnight check therefore does not skip the later verification of newly updated
morning data. Failed attempts
back off at least an hour. Outages may use last verified effective schedules with
an explicit stale warning, up to the configured maximum age (default seven days).
If no usable verified schedule exists, an explicitly configured ex-VAT manual
fallback may be used with a warning; otherwise the price update fails closed.
Manual mode never fetches or overwrites user-locked values. No opaque VATClass,
unknown unit, null hour, negative rate, overlap or truncated response is accepted.

The decoder is provider-neutral, but only Radius C has a verified native preset.
Other DSOs use an explicitly configured external tariff sensor until their
identity, category and VAT convention are verified. No fuzzy auto-selection.

## Dated public policy and contract decision

Issue #8 supplies Energinet's 2026 network/system amounts (4.3/7.2 øre ex VAT) and
universal electricity tax 0.8 øre ex VAT in 2026–2027. The optional policy adapter
uses **only those stated periods** and cites the owner's issue as its source; it
is not a live legislative discovery service. Unknown later network/tax rates
require verified dated rules and never inherit old values silently.

Supplier markup is contract-specific. Neither legacy EWII 3.75 øre nor advertised
6.5 øre is selected automatically. The owner's actual per-site contract amount,
VAT inclusion and effective period are required. Until provided, dated all-in
pricing is unavailable rather than assuming a free supplier component.

Every dated component declares amount, unit, VAT inclusion/rate, source, verification
date and half-open effective dates. Locked manual rules win over public policy
within their stated period. Electric-heating eligibility is explicit owner-confirmed
registration plus an annual-usage year/value; no BBR or billing inference. The
universal 2026–2027 tax is identical on either side of 4000 kWh. Unknown future
eligibility/tax policies are not invented. Monthly subscriptions are reported
separately and never amortized into marginal charging prices.
