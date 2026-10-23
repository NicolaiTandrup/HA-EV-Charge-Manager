"""Dated public rates, contract markup, per-component VAT and eligibility."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pytest

from custom_components.ev_charge_manager.planner import PriceSlot
from custom_components.ev_charge_manager.price_components import (
    compose_dated,
    danish_public_components,
)


def rule(name, amount, **changes):
    return {
        "id": name,
        "amount": amount,
        "unit": "ore/kWh",
        "vat_included": False,
        "vat_rate": 0.25,
        "valid_from": "2026-01-01",
        "valid_to": "2027-01-01",
        "source": "Verified test contract",
        "verified_on": "2026-10-23",
        **changes,
    }


def tariff():
    return {
        "mode": "spot_ex_vat",
        "vat": 0.25,
        "grid": 0,
        "components": danish_public_components() + [rule("supplier", 3.75, vat_included=True)],
    }


def slot(year=2026, price=1):
    start = datetime(year, 10, 24, 12, tzinfo=UTC)
    return PriceSlot(start, start + timedelta(minutes=15), price)


@pytest.mark.parametrize("price,included", [(1, False), (1.25, True), (-0.5, False)])
def test_component_vat_exactly_once_and_negative_spot(price, included):
    config = tariff()
    config["mode"] = "spot_incl_vat" if included else "spot_ex_vat"
    total, parts = compose_dated(slot(price=price), config)
    expected_spot = price if included else price * 1.25
    assert total == pytest.approx(expected_spot + 0.05375 + 0.09 + 0.01 + 0.0375)
    assert parts["components"]["supplier"]["incl_vat"] == 0.0375


def test_contract_is_required_and_post2026_network_rates_not_invented():
    config = tariff()
    with pytest.raises(ValueError, match="Missing verified"):
        compose_dated(slot(2027), config)
    config["components"] = danish_public_components()
    with pytest.raises(ValueError, match="Missing verified"):
        compose_dated(slot(), config)


@pytest.mark.parametrize(
    "year,usage,registered",
    [(2026, 3999, False), (2026, 4001, True), (2027, 4000, True), (2027, 4001, True)],
)
def test_universal_2026_2027_tax_not_an_invented_heating_discount(year, usage, registered):
    config = tariff()
    config.update(annual_usage_kwh=usage, usage_year=year, heating_registered=registered)
    if year == 2027:
        # Explicitly supplied future network/contract rates, not auto-extrapolation.
        config["components"] = [r for r in config["components"] if r["id"] == "electricity_tax"] + [
            rule("energinet_net", 4.3, valid_from="2027-01-01", valid_to="2028-01-01"),
            rule("energinet_system", 7.2, valid_from="2027-01-01", valid_to="2028-01-01"),
            rule(
                "supplier", 3.75, vat_included=True, valid_from="2027-01-01", valid_to="2028-01-01"
            ),
        ]
    _, parts = compose_dated(slot(year), config)
    assert parts["components"]["electricity_tax"]["incl_vat"] == 0.01


def test_locked_rate_and_subscription_not_amortized():
    config = tariff()
    base, _ = compose_dated(slot(), config)
    config["components"] += [
        rule("energinet_net", 8, locked=True),
        rule("subscription", 50, unit="DKK/month", vat_included=True),
    ]
    total, parts = compose_dated(slot(), config)
    assert total == pytest.approx(base - 0.05375 + 0.1)
    assert parts["fixed_subscriptions_excluded"][0]["incl_vat"] == 50
    assert parts["components"]["energinet_net"]["locked"]


def test_conflicting_versions_and_unknown_units_fail():
    config = tariff()
    config["components"].append(deepcopy(config["components"][0]))
    with pytest.raises(ValueError, match="Overlapping"):
        compose_dated(slot(), config)
    config = tariff()
    config["components"][-1]["unit"] = "unknown"
    with pytest.raises(ValueError, match="unit"):
        compose_dated(slot(), config)
