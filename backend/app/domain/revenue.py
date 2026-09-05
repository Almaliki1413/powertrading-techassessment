"""Signed energy-market cash flow. No price-sign branch is permitted."""

from __future__ import annotations

from decimal import Decimal

from app.domain.battery import interval_energy_mwh
from app.domain.models import BatteryConfig


def interval_cash_flow_aud(
    rrp_aud_per_mwh: Decimal,
    charge_mw: Decimal,
    discharge_mw: Decimal,
    config: BatteryConfig,
) -> Decimal:
    """CashFlow_t = RRP_t * (discharge_t - charge_t) * Δt."""
    return rrp_aud_per_mwh * (
        interval_energy_mwh(discharge_mw, config) - interval_energy_mwh(charge_mw, config)
    )


def total_revenue_aud(
    prices: tuple[Decimal, ...],
    charge_mw: tuple[Decimal, ...],
    discharge_mw: tuple[Decimal, ...],
    config: BatteryConfig,
) -> Decimal:
    return sum(
        (
            interval_cash_flow_aud(rrp, ch, dis, config)
            for rrp, ch, dis in zip(prices, charge_mw, discharge_mw, strict=True)
        ),
        Decimal("0"),
    )


def throughput_mwh(
    charge_mw: tuple[Decimal, ...],
    discharge_mw: tuple[Decimal, ...],
    config: BatteryConfig,
) -> Decimal:
    return sum(
        (
            interval_energy_mwh(ch, config) + interval_energy_mwh(dis, config)
            for ch, dis in zip(charge_mw, discharge_mw, strict=True)
        ),
        Decimal("0"),
    )
