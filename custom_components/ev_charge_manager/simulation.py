"""Bounded reversible probe simulation. Synthetic samples never become live identity."""

from math import isfinite


def simulate_probe(
    charger,
    candidates,
    samples,
    *,
    commissioned_vehicles,
    commissioned_chargers,
    guest=False,
    max_probes=2,
):
    """Model response discrimination without sending a command or reading a device.

    Each synthetic sample maps candidate ID to observed change in kW. A single
    positive respondent may resolve the simulation. Zero/multiple responses never
    select an identity. Every modeled pulse has a modeled restoration.
    """
    if (
        guest
        or charger not in commissioned_chargers
        or not set(candidates) <= set(commissioned_vehicles)
    ):
        return {"vehicle": None, "reason": "not_commissioned_or_guest", "trace": []}
    trace = []
    for sample in samples[: max(0, min(max_probes, 2))]:
        trace.append({"step": "simulated_pulse", "charger": charger})
        trace.append({"step": "simulated_restore", "charger": charger})
        if set(sample) != set(candidates) or any(
            not isinstance(v, (int, float)) or not isfinite(v) for v in sample.values()
        ):
            continue
        matches = [key for key, value in sample.items() if value > 0.5]
        if len(matches) == 1:
            return {"vehicle": matches[0], "reason": "synthetic_response", "trace": trace}
    return {"vehicle": None, "reason": "ambiguous", "trace": trace}
