"""Date-aware, separately verified and VAT-normalized marginal components."""

from datetime import date
from math import isfinite
from zoneinfo import ZoneInfo

REQUIRED = {"energinet_net", "energinet_system", "electricity_tax", "supplier"}


def danish_public_components():
    """Issue #8 verified policy periods only; never extrapolate unknown years.

    The owner supplied these 2026/2027 rates in #8. This is a dated policy adapter,
    not a claim of live legislation scraping or a customer's supplier contract.
    """
    result = []
    for name, amount, end in [
        ("energinet_net", 4.3, "2027-01-01"),
        ("energinet_system", 7.2, "2027-01-01"),
        ("electricity_tax", 0.8, "2028-01-01"),
    ]:
        result.append(
            {
                "id": name,
                "amount": amount,
                "unit": "ore/kWh",
                "vat_included": False,
                "vat_rate": 0.25,
                "valid_from": "2026-01-01",
                "valid_to": end,
                "source": "Rate specified by owner: Manager issue #8",
                "verified_on": "2026-10-23",
                "eligibility": "all",
            }
        )
    return result


def normalize_component(rule):
    amount = float(rule["amount"])
    rate = float(rule["vat_rate"])
    if not isfinite(amount) or amount < 0 or not isfinite(rate) or not 0 <= rate <= 1:
        raise ValueError("Invalid component amount/VAT")
    if (
        rule["unit"] not in {"DKK/kWh", "ore/kWh", "DKK/month"}
        or type(rule["vat_included"]) is not bool
    ):
        raise ValueError("Explicit component unit and VAT inclusion required")
    if not rule.get("source") or not rule.get("verified_on"):
        raise ValueError("Component source and verification date required")
    date.fromisoformat(rule["verified_on"])
    amount /= 100 if rule["unit"] == "ore/kWh" else 1
    ex = amount / (1 + rate) if rule["vat_included"] else amount
    gross = amount if rule["vat_included"] else amount * (1 + rate)
    return {
        "id": rule["id"],
        "unit": "DKK/month" if rule["unit"] == "DKK/month" else "DKK/kWh",
        "ex_vat": ex,
        "vat": gross - ex,
        "incl_vat": gross,
        "source": rule["source"],
        "valid_from": rule["valid_from"],
        "valid_to": rule["valid_to"],
        "verified_on": rule["verified_on"],
        "locked": rule.get("locked", False),
        "eligibility": rule.get("eligibility", "all"),
    }


def validate_rules(rules):
    if not isinstance(rules, list):
        raise ValueError("Dated component rules must be a list")
    for rule in rules:
        if not isinstance(rule, dict):
            raise ValueError("Invalid dated rule")
        normalize_component(rule)
        if date.fromisoformat(rule["valid_to"]) <= date.fromisoformat(rule["valid_from"]):
            raise ValueError("Invalid component effective range")


def compose_dated(slot, tariff):
    if tariff.get("mode") not in {"spot_ex_vat", "spot_incl_vat"}:
        raise ValueError("Dated components cannot be added to all-in input")
    if any(tariff.get(key, 0) for key in ("tax", "supplier")):
        raise ValueError("Dated and legacy tax/supplier fees would be duplicated")
    day = slot.start.astimezone(ZoneInfo(tariff.get("timezone", "Europe/Copenhagen"))).date()
    rules = tariff["components"]
    if not isinstance(rules, list):
        raise ValueError("Dated components must be a list")
    active = {}
    fixed = []
    for rule in rules:
        start, end = date.fromisoformat(rule["valid_from"]), date.fromisoformat(rule["valid_to"])
        if end <= start:
            raise ValueError("Invalid component effective period")
        if not start <= day < end:
            continue
        if rule.get("eligibility", "all") == "heating_above_4000":
            if not isfinite(float(tariff.get("annual_usage_kwh", 0))):
                raise ValueError("Invalid verified annual usage")
            if (
                not tariff.get("heating_registered")
                or tariff.get("usage_year") != day.year
                or tariff.get("annual_usage_kwh", 0) <= 4000
            ):
                continue
        elif rule.get("eligibility", "all") != "all":
            raise ValueError("Unverified eligibility class")
        component = normalize_component(rule)
        if rule["unit"] == "DKK/month":
            fixed.append(component)
            continue
        name = rule["id"]
        if name in active:
            previous = active[name]
            score = (component["locked"], component["eligibility"] == "heating_above_4000")
            old_score = (previous["locked"], previous["eligibility"] == "heating_above_4000")
            if score == old_score:
                raise ValueError("Overlapping component rate versions")
            if score < old_score:
                continue
        active[name] = component
    if not REQUIRED <= active.keys():
        raise ValueError("Missing verified component for requested date/contract")
    vat = float(tariff["vat"])
    if not isfinite(vat) or not 0 <= vat <= 1:
        raise ValueError("Invalid spot/grid VAT")
    spot_ex = slot.price / (1 + vat) if tariff["mode"] == "spot_incl_vat" else slot.price
    grid = float(tariff.get("grid", 0))
    if "grid_slots" in tariff:
        matching = [s for s in tariff["grid_slots"] if s.start <= slot.start and s.end >= slot.end]
        if len(matching) != 1:
            raise ValueError("Missing/overlapping grid tariff")
        grid += matching[0].price
    if not isfinite(grid) or grid < 0:
        raise ValueError("Invalid grid component")
    active["spot"] = {
        "id": "spot",
        "ex_vat": spot_ex,
        "vat": spot_ex * vat,
        "incl_vat": slot.price if tariff["mode"] == "spot_incl_vat" else slot.price * (1 + vat),
    }
    active["dso"] = {"id": "dso", "ex_vat": grid, "vat": grid * vat, "incl_vat": grid * (1 + vat)}
    return sum(c["incl_vat"] for c in active.values()), {
        "components": active,
        "fixed_subscriptions_excluded": fixed,
    }
