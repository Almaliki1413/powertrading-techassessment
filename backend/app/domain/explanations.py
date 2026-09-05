"""Deterministic reason engine. Does not invent local-threshold causality for a global MILP."""

from __future__ import annotations

from decimal import Decimal

from app.domain.battery import next_soc_mwh, power_snap_tolerance_mw
from app.domain.models import Action, BatteryConfig, ReasonCode
from app.domain.revenue import total_revenue_aud


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


def contrast_interval(
    *,
    index: int,
    charge_mw: tuple[Decimal, ...],
    discharge_mw: tuple[Decimal, ...],
    prices: tuple[Decimal, ...],
    config: BatteryConfig,
) -> str:
    snap = power_snap_tolerance_mw(config)
    charge = tuple(Decimal("0") if abs(v) <= snap else v for v in charge_mw)
    discharge = tuple(Decimal("0") if abs(v) <= snap else v for v in discharge_mw)
    chosen = classify_action(charge[index], discharge[index], snap)
    alternatives: list[tuple[str, Decimal, Decimal]] = []
    if chosen != "idle":
        alternatives.append(("Idle", Decimal("0"), Decimal("0")))
    if chosen == "charge":
        alternatives.append(("Discharge instead", Decimal("0"), charge[index]))
    elif chosen == "discharge":
        alternatives.append(("Charge instead", discharge[index], Decimal("0")))
    else:
        alternatives.append(("Charge", config.charge_limit_mw, Decimal("0")))
        alternatives.append(("Discharge", Decimal("0"), config.discharge_limit_mw))

    _, _, base_revenue = _replay_fixed_rest(charge, discharge, prices, config)
    parts: list[str] = []
    for label, alt_charge, alt_discharge in alternatives:
        trial_charge = list(charge)
        trial_discharge = list(discharge)
        trial_charge[index] = alt_charge
        trial_discharge[index] = alt_discharge
        feasible, failure, revenue = _replay_fixed_rest(
            tuple(trial_charge), tuple(trial_discharge), prices, config
        )
        if not feasible:
            parts.append(
                f"{label} is infeasible with later intervals held fixed: {_failure_clause(failure)}."
            )
            continue
        delta = (revenue - base_revenue).quantize(Decimal("0.01"))
        if delta < 0:
            parts.append(
                f"{label} would lower day revenue by {abs(delta)} AUD with later intervals held fixed."
            )
        elif delta > 0:
            parts.append(
                f"{label} would raise day revenue by {delta} AUD with later intervals held fixed; "
                "that local swap is not the global three-stage schedule."
            )
        else:
            parts.append(
                f"{label} would match day revenue with later intervals held fixed; "
                "the chosen action comes from the global solve, not a local threshold."
            )
    return " ".join(parts)


def _failure_clause(kind: str) -> str:
    if kind == "SoC_min":
        return "SoC would fall below 0 MWh"
    if kind == "SoC_max":
        return "SoC would exceed 200 MWh"
    if kind == "terminal_soc":
        return "the 100 MWh terminal target would be missed"
    if kind == "power":
        return "a power limit would be violated"
    return kind.replace("_", " ")


def _replay_fixed_rest(
    charge_mw: tuple[Decimal, ...],
    discharge_mw: tuple[Decimal, ...],
    prices: tuple[Decimal, ...],
    config: BatteryConfig,
) -> tuple[bool, str, Decimal]:
    snap = power_snap_tolerance_mw(config)
    soc = config.initial_soc_mwh
    for charge, discharge, rrp in zip(charge_mw, discharge_mw, prices, strict=True):
        charge = Decimal("0") if abs(charge) <= snap else charge
        discharge = Decimal("0") if abs(discharge) <= snap else discharge
        if charge > Decimal("0") and discharge > Decimal("0"):
            return False, "simultaneous", Decimal("0")
        if charge > config.charge_limit_mw + config.soc_tolerance_mwh:
            return False, "power", Decimal("0")
        if discharge > config.discharge_limit_mw + config.soc_tolerance_mwh:
            return False, "power", Decimal("0")
        soc = next_soc_mwh(soc, charge, discharge, config)
        if soc < -config.soc_tolerance_mwh:
            return False, "SoC_min", Decimal("0")
        if soc > config.capacity_mwh + config.soc_tolerance_mwh:
            return False, "SoC_max", Decimal("0")
    revenue = total_revenue_aud(prices, charge_mw, discharge_mw, config)
    if abs(soc - config.terminal_soc_mwh) > config.soc_tolerance_mwh * 2:
        return False, "terminal_soc", revenue
    return True, "", revenue


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
