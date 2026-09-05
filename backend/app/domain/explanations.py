"""Deterministic reason engine. Does not invent local-threshold causality for a global MILP."""

from __future__ import annotations

from decimal import Decimal

from app.domain.models import Action, BatteryConfig, ReasonCode


def price_percentile(rrp: Decimal, all_rrp: tuple[Decimal, ...]) -> Decimal:
    if not all_rrp:
        return Decimal("0")
    n = len(all_rrp)
    rank = sum(1 for other in all_rrp if other <= rrp)
    return (Decimal(rank) / Decimal(n)) * Decimal("100")


def classify_action(charge_mw: Decimal, discharge_mw: Decimal, tolerance: Decimal) -> Action:
    if discharge_mw > tolerance:
        return "discharge"
    if charge_mw > tolerance:
        return "charge"
    return "idle"


def explain(
    *,
    action: Action,
    charge_mw: Decimal,
    discharge_mw: Decimal,
    soc_before: Decimal,
    soc_after: Decimal,
    rrp: Decimal,
    percentile: Decimal,
    config: BatteryConfig,
    remaining_intervals: int,
) -> tuple[ReasonCode, str, tuple[str, ...]]:
    bindings: list[str] = []
    tol = config.soc_tolerance_mwh
    power_headroom_charge = config.charge_limit_mw - charge_mw
    power_headroom_discharge = config.discharge_limit_mw - discharge_mw

    at_soc_min = soc_after <= tol or soc_before <= tol
    at_soc_max = soc_after >= config.capacity_mwh - tol or soc_before >= config.capacity_mwh - tol
    at_charge_power = action == "charge" and power_headroom_charge <= tol
    at_discharge_power = action == "discharge" and power_headroom_discharge <= tol

    if at_soc_min:
        bindings.append("SoC_min")
    if at_soc_max:
        bindings.append("SoC_max")
    if at_charge_power or at_discharge_power:
        bindings.append("power_limit")

    energy_needed = config.terminal_soc_mwh - soc_after
    max_remaining_charge = (
        config.eta_charge * config.charge_limit_mw * config.interval_hours * Decimal(max(remaining_intervals, 0))
    )
    max_remaining_discharge = (
        (config.discharge_limit_mw * config.interval_hours * Decimal(max(remaining_intervals, 0)))
        / config.eta_discharge
    )
    terminal_binding = False
    if remaining_intervals >= 0:
        if energy_needed > max_remaining_charge + config.soc_tolerance_mwh:
            terminal_binding = True
        if -energy_needed > max_remaining_discharge + config.soc_tolerance_mwh:
            terminal_binding = True
        slack_to_terminal = abs(config.terminal_soc_mwh - soc_after)
        if slack_to_terminal <= config.soc_tolerance_mwh and remaining_intervals == 0:
            terminal_binding = True
    if terminal_binding:
        bindings.append("terminal_soc")

    if at_soc_min and action != "charge":
        code: ReasonCode = "BOUND_SOC_MIN"
        text = (
            f"Minimum SoC is active at {soc_after:.6f} MWh and limits further discharge "
            f"at RRP {rrp} AUD/MWh (price percentile {percentile:.1f}%)."
        )
    elif at_soc_max and action != "discharge":
        code = "BOUND_SOC_MAX"
        text = (
            f"Maximum SoC is active at {soc_after:.6f} MWh and limits further charge "
            f"at RRP {rrp} AUD/MWh (price percentile {percentile:.1f}%)."
        )
    elif at_charge_power or at_discharge_power:
        code = "BOUND_POWER"
        text = (
            f"{action.capitalize()} reaches the 100 MW power limit at RRP {rrp} AUD/MWh "
            f"(price percentile {percentile:.1f}%)."
        )
    elif terminal_binding and action != "idle":
        code = "TERMINAL_TARGET"
        text = (
            f"The 100 MWh terminal inventory target constrains this {action} at RRP {rrp} AUD/MWh "
            f"with {remaining_intervals} intervals remaining."
        )
    elif action == "charge":
        code = "ECONOMIC_CHARGE"
        text = (
            f"Charge is selected by the global perfect-hindsight optimum at RRP {rrp} AUD/MWh "
            f"(price percentile {percentile:.1f}%). This is not a local threshold rule."
        )
    elif action == "discharge":
        code = "ECONOMIC_DISCHARGE"
        text = (
            f"Discharge is selected by the global perfect-hindsight optimum at RRP {rrp} AUD/MWh "
            f"(price percentile {percentile:.1f}%). This is not a local threshold rule."
        )
    else:
        # Idle after lexicographic throughput/idle stages, or globally unused.
        if abs(rrp) <= Decimal("1"):
            code = "IDLE_TIE_BREAK"
            text = (
                f"Idle after lexicographic tie-break: additional cycling at RRP {rrp} AUD/MWh "
                f"would not improve revenue."
            )
        else:
            code = "IDLE_GLOBAL_OPTIMUM"
            text = (
                f"No charge or discharge is selected by the global optimum at RRP {rrp} AUD/MWh "
                f"(price percentile {percentile:.1f}%; SoC {soc_before:.6f} → {soc_after:.6f} MWh)."
            )

    return code, text, tuple(bindings)
