# Port provenance and licensing

The repository owner explicitly requested reuse of both native drafts. This port
keeps the working Python algorithms rather than rebuilding the planner/association
logic from requirements. Root LICENSE is MIT, copyright Nicolai Tandrup (2026).
The Brain contributor MIT notice is preserved in `docs/upstream/brain/LICENSE`.
The Optimizer source tree has no LICENSE file at the reviewed commit; this port is
made under the owner's explicit reuse instruction, not a claim that the historical
Optimizer repository already carried MIT. Confirm contributor rights before wider
distribution if any third-party contribution exists there.

| Source | Reviewed PR head | Port |
| --- | --- | --- |
| NicolaiTandrup/HA-EV-Charger-Brain draft PR #2 | `6236d5381dfbd51239313a48ec499fd66073ff56` | `engine.py` → `brain.py`, pure engine tests, reference docs and original Node-RED export |
| NicolaiTandrup/HA-ev-charge-optimizer draft PR #2 | `9f446c6b06ac4a8dba0a94d8826ab0f73aa3a7e1` | planner, price adapter, history, coordinator adapter, planner/history/JavaScript parity tests, dev dependency lock and reference docs |

Upstream documents under `docs/upstream/` are historical verbatim references; their
old domains, release gates and limitations are not the current configuration guide.
The new coordinator bridges one shared registry into the original planner's input
contract. Historical HA lifecycle/config-flow tests are replaced by unified-domain
lifecycle/configuration/safety tests because their old config entry shapes differ.
The original Node-RED fixtures retain legacy entity names deliberately; changing
those names would change the executable parity oracle.

Node-RED files are copied byte-for-byte, are never imported into a running flow,
and retain production routing/commands as reference data only.
