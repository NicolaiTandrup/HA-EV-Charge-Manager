# Native availability, eligibility and charger limits

Configure → Device availability and eligibility selects any vehicle, charger or
site. Existing entries remain enabled and unrestricted until deliberately changed.
Disabling never deletes history, grants authority or sends a stop command.

Vehicles can restrict applicable sites. Chargers can restrict eligible known
vehicles, select an explicit configured site, specify maximum AC charging power,
and choose manual simulated guest authorization or deny it. A restricted empty
list permits nobody/no site; it never means unrestricted. Missing selected IDs
fail closed. Explicit site selection must agree with the site's zone. These are
many-to-many eligibility rules, never permanent one-car/one-charger assignments.

Disabled/disallowed resources cannot become managed plans. Physical charger status
and plug/unplug still reconcile, so an occupied disabled charger is not assumed
to consume zero supply. Unknown connected demand retains the existing conservative
site-capacity guard. Known car forecast power is capped by both the configured car
maximum and its associated charger's maximum; existing shared-supply allocation,
SoC priorities, deadlines, boost and tie policy are unchanged.

Guest authorization remains explicit, session-scoped and simulated only. Denied
or disabled chargers cannot receive new simulated guest permission or command
proposals. Policy changes reload safely, preserve accounting and do not automatically
restore authority. These fields are not live commissioning controls.
