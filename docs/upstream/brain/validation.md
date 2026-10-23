# Validation record

Validated locally on 2026-10-23 with Python 3.14.8 and Home Assistant 2026.10.2.

* 26 synthetic tests passed, none skipped or expected-failing.
* Coverage: 93% of integration statements; pure engine 100%.
* Ruff lint and format checks passed.
* Official hassfest container passed: one integration, zero invalid integrations.
  Image digest: sha256:2dce3c5423a600e7965e5a3d5a95e0707e8452fb001ab2b5d0602099bbecba92.
* Hashed dependency sync and the complete saved cloud install script passed.
* HA fixture entities verified: sensor.ev_charger_assignments,
  binary_sensor.charger_one_association_valid and the second charger counterpart.
  Sources were registered synthetic sensors, switches, binary sensors and trackers;
  these are not claims about the owner's actual entities or hardware.
* Tests cover two sites/vehicles/chargers, ambiguity on both graph sides,
  disconnect/reconnect, history suppression, manual latch, GPS unknown, cable off,
  missing/stale sources, primary/fallback precedence, restart reconstruction,
  simulated loss of source reports, event publication, watchdog expiry,
  source/device validation, config/options, diagnostics, unload and zero services.

HACS structure was checked against the current official integration documentation,
including local brand icons. Remote hassfest also passed. The first CI run found a
pip cache path error, corrected by explicitly naming requirements-dev.txt. The
HACS action executed 10 checks: 8 passed, while repository topics and license
metadata failed. The license file is in this PR, but GitHub's repository license
metadata reflects the default branch until merge. Adding topics was attempted
and rejected with “Resource not accessible by integration”; the owner must add
home-assistant, hacs and ev-charging topics in GitHub repository settings. Do not
ignore those checks or describe HACS as fully validated before they pass.

GitHub API requests initially received CONNECT 403; api.github.com was added to
the cloud configuration draft, and subsequent requests succeeded. Draft PR #2 is
open. The contract proposal was posted to Honeycomb Menu NG issue #126; this is
coordination evidence, not consumer implementation or maintainer acknowledgement.

No owner HA installation, physical charging control, stable release, prerelease,
repository rename, official HACS catalog submission or Honeycomb acknowledgement
has occurred. Manual-latch restart persistence and exact legacy timing behaviors
remain separate follow-up work before a production-control phase.
