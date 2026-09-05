"""Battery energy and power equations. Efficiency lives only in the SoC transition."""

from __future__ import annotations

from decimal import Decimal

from app.domain.models import BatteryConfig

def power_snap_tolerance_mw(config: BatteryConfig) -> Decimal:
    return max(config.soc_tolerance_mwh, config.throughput_tolerance_mwh / config.interval_hours)


def interval_energy_mwh(power_mw: Decimal, config: BatteryConfig) -> Decimal:
    """Convert MW over one five-minute interval to MWh."""
    return power_mw * config.interval_hours


def next_soc_mwh(
    soc_before_mwh: Decimal,
    charge_mw: Decimal,
    discharge_mw: Decimal,
    config: BatteryConfig,
) -> Decimal:
    imported = interval_energy_mwh(charge_mw, config)
    exported = interval_energy_mwh(discharge_mw, config)
    return soc_before_mwh + (config.eta_charge * imported) - (exported / config.eta_discharge)


def signed_power_mw(charge_mw: Decimal, discharge_mw: Decimal) -> Decimal:
    """Export is positive; import is negative."""
    return discharge_mw - charge_mw
