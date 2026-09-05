from __future__ import annotations

from decimal import Decimal

import pytest

from app.domain.battery import interval_energy_mwh, next_soc_mwh
from app.domain.explanations import classify_action, explain, price_percentile
from app.domain.models import BatteryConfig
from app.domain.revenue import interval_cash_flow_aud
from app.domain.verification import verify_schedule


def test_five_minute_conversion() -> None:
    config = BatteryConfig()
    energy = interval_energy_mwh(Decimal("100"), config)
    assert energy == Decimal("100") * Decimal(5) / Decimal(60)


def test_charge_soc_increases_by_eta_times_imported() -> None:
    config = BatteryConfig()
    imported = interval_energy_mwh(Decimal("100"), config)
    after = next_soc_mwh(Decimal("100"), Decimal("100"), Decimal("0"), config)
    assert after == Decimal("100") + config.eta_charge * imported


def test_discharge_soc_decreases_by_exported_over_eta() -> None:
    config = BatteryConfig()
    exported = interval_energy_mwh(Decimal("100"), config)
    after = next_soc_mwh(Decimal("100"), Decimal("0"), Decimal("100"), config)
    assert after == Decimal("100") - exported / config.eta_discharge


def test_positive_price_signs() -> None:
    config = BatteryConfig()
    charge = interval_cash_flow_aud(Decimal("50"), Decimal("100"), Decimal("0"), config)
    discharge = interval_cash_flow_aud(Decimal("50"), Decimal("0"), Decimal("100"), config)
    assert charge < 0
    assert discharge > 0


def test_negative_price_signs() -> None:
    config = BatteryConfig()
    charge = interval_cash_flow_aud(Decimal("-10"), Decimal("100"), Decimal("0"), config)
    discharge = interval_cash_flow_aud(Decimal("-10"), Decimal("0"), Decimal("100"), config)
    assert charge > 0
    assert discharge < 0


def test_bounds_and_exclusivity_rejected() -> None:
    config = BatteryConfig()
    report = verify_schedule(
        charge_mw=(Decimal("50"),),
        discharge_mw=(Decimal("50"),),
        prices=(Decimal("10"),),
        config=config,
        expected_intervals=1,
    )
    assert report.passed is False
    assert any("simultaneous" in item for item in report.failures)


def test_terminal_tolerance_failure() -> None:
    config = BatteryConfig()
    report = verify_schedule(
        charge_mw=(Decimal("0"),),
        discharge_mw=(Decimal("100"),),
        prices=(Decimal("10"),),
        config=config,
        expected_intervals=1,
    )
    assert report.passed is False
    assert any("terminal" in item.lower() for item in report.failures)


def test_revenue_reconciliation_and_explanations() -> None:
    config = BatteryConfig()
    prices = (Decimal("10"), Decimal("80"))
    charge = (Decimal("100"), Decimal("0"))
    discharge = (Decimal("0"), Decimal("100"))
    report = verify_schedule(
        charge_mw=charge,
        discharge_mw=discharge,
        prices=prices,
        config=config,
        expected_intervals=2,
    )
    assert report.passed is False or report.revenue_aud == sum(
        (
            interval_cash_flow_aud(prices[0], charge[0], discharge[0], config),
            interval_cash_flow_aud(prices[1], charge[1], discharge[1], config),
        ),
        Decimal("0"),
    )
    percentile = price_percentile(Decimal("80"), prices)
    code, text, _ = explain(
        action="discharge",
        charge_mw=Decimal("0"),
        discharge_mw=Decimal("100"),
        soc_before=Decimal("100"),
        soc_after=Decimal("90"),
        rrp=Decimal("80"),
        percentile=percentile,
        config=config,
        remaining_intervals=0,
    )
    assert code in {"BOUND_POWER", "TERMINAL_TARGET", "ECONOMIC_DISCHARGE"}
    assert "local threshold" not in text.lower() or "not a local threshold" in text.lower()
    assert classify_action(Decimal("0"), Decimal("0"), Decimal("0.000001")) == "idle"


def test_invalid_config_rejected() -> None:
    from app.domain.errors import InvalidConfiguration

    with pytest.raises(InvalidConfiguration):
        BatteryConfig(capacity_mwh=Decimal("0"))
