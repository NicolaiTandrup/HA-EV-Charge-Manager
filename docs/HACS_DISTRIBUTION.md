# HACS distribution gate

**Normal HACS custom-repository installation is currently blocked.** Main still
contains only LICENSE/README. A manually test-installable ZIP and passing HACS
validation do not make this an owner-installable HACS beta.

The latest producer handoff records the owner's PAHA02-DEV failure and executable
HACS 2.0.5/development workflow tests. See the authoritative paired evidence in
[PE distribution guide](https://github.com/NicolaiTandrup/HA-Energy-Price-Engine/blob/feat/standalone-price-engine/docs/HACS_DISTRIBUTION.md).
HACS discards /tree/branch URL suffixes in normal custom repository registration;
do not suggest one as a branch selection workaround or invent an unpublished
version. The source ZIP is a separate manual test-installation route.

Reviewable choices require explicit owner authorization:
1. Review the cumulative stack/base sequence and merge the complete integrations
   into their existing default branches. HACS can install an approved default branch
   without necessarily publishing a release; releasing remains separately approved.
2. Change default branches to frozen reviewed beta branches. This changes repository
   behavior globally and is not an authorized local packaging fix.
3. Create a separately approved beta distribution repository with full source,
   metadata, license/provenance and update ownership.

No such action is authorized or performed here. Preserve all existing PRs and
branches; no destructive rebase, force push, new repository, tag or release.
The cumulative feature branch and ZIP remain reviewable without altering main.

After approval and actual distribution changes, validate normal HACS add/download,
restart, Devices & services add/configure/options/reload on PAHA02-DEV. Record HA OS,
Core, HACS and provider versions and exact installed commits. Source/ZIP tests are
not evidence that this owner installation succeeded. Production remains untouched.
