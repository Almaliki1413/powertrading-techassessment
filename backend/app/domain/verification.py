"""Independent post-solve verifier. Must not import PuLP."""

from __future__ import annotations

from decimal import Decimal

from app.domain.battery import interval_energy_mwh, next_soc_mwh, power_snap_tolerance_mw, signed_power_mw
from app.domain.models import BatteryConfig, VerificationReport
from app.domain.revenue import interval_cash_flow_aud


def _snap(value: Decimal, tolerance: Decimal) -> Decimal:
    if abs(value) <= tolerance:
        return Decimal("0")
    return value


def _power_tolerance(config: BatteryConfig) -> Decimal:
    return power_snap_tolerance_mw(config)


def verify_schedule(
    *,
    charge_mw: tuple[Decimal, ...],
    discharge_mw: tuple[Decimal, ...],
    prices: tuple[Decimal, ...],
    config: BatteryConfig,
    expected_intervals: int = 288,
) -> VerificationReport:
    failures: list[str] = []
    n = len(charge_mw)
    if n != expected_intervals or n != len(discharge_mw) or n != len(prices):
        failures.append(
            f"expected {expected_intervals} decisions, got charge={n} "
            f"discharge={len(discharge_mw)} prices={len(prices)}"
        )
        return VerificationReport(
            passed=False,
            interval_count=n,
            revenue_aud=Decimal("0"),
            throughput_mwh=Decimal("0"),
            imported_mwh=Decimal("0"),
            exported_mwh=Decimal("0"),
            ending_soc_mwh=config.initial_soc_mwh,
            equivalent_full_cycles=Decimal("0"),
            failures=tuple(failures),
        )

    soc = config.initial_soc_mwh
    if abs(soc - config.initial_soc_mwh) > config.soc_tolerance_mwh:
        failures.append("initial SoC mismatch")

    revenue = Decimal("0")
    imported = Decimal("0")
    exported = Decimal("0")
    zero = Decimal("0")

    for t, (ch_raw, dis_raw, rrp) in enumerate(zip(charge_mw, discharge_mw, prices, strict=True)):
        ch = _snap(ch_raw, _power_tolerance(config))
        dis = _snap(dis_raw, _power_tolerance(config))
        if ch > zero and dis > zero:
            failures.append(f"t={t}: simultaneous charge and discharge")
        if ch < zero or dis < zero:
            failures.append(f"t={t}: negative power")
        if ch > config.charge_limit_mw + config.soc_tolerance_mwh:
            failures.append(f"t={t}: charge exceeds {config.charge_limit_mw} MW")
        if dis > config.discharge_limit_mw + config.soc_tolerance_mwh:
            failures.append(f"t={t}: discharge exceeds {config.discharge_limit_mw} MW")

        imported_t = interval_energy_mwh(ch, config)
        exported_t = interval_energy_mwh(dis, config)
        imported += imported_t
        exported += exported_t
        soc_after = next_soc_mwh(soc, ch, dis, config)
        if soc_after < -config.soc_tolerance_mwh or soc_after > config.capacity_mwh + config.soc_tolerance_mwh:
            failures.append(f"t={t}: SoC {soc_after} outside [0, {config.capacity_mwh}]")
        revenue += interval_cash_flow_aud(rrp, ch, dis, config)
        _ = signed_power_mw(ch, dis)
        soc = soc_after

    if abs(soc - config.terminal_soc_mwh) > config.soc_tolerance_mwh * 2:
        failures.append(f"terminal SoC {soc} != {config.terminal_soc_mwh}")

    throughput = imported + exported
    cycles = throughput / (Decimal("2") * config.capacity_mwh) if config.capacity_mwh else Decimal("0")
    return VerificationReport(
        passed=not failures,
        interval_count=n,
        revenue_aud=revenue,
        throughput_mwh=throughput,
        imported_mwh=imported,
        exported_mwh=exported,
        ending_soc_mwh=soc,
        equivalent_full_cycles=cycles,
        failures=tuple(failures),
    )
