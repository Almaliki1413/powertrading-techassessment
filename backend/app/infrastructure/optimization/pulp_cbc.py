"""PuLP/CBC three-stage lexicographic perfect-hindsight MILP. No silent solver fallback."""

from __future__ import annotations

import hashlib
import time
from decimal import Decimal
from pathlib import Path

import pulp
from pulp import PULP_CBC_CMD, LpBinary, LpMaximize, LpMinimize, LpProblem, LpStatus, LpVariable, lpSum, value

from app.domain.battery import interval_energy_mwh, next_soc_mwh, power_snap_tolerance_mw, signed_power_mw
from app.domain.errors import SolverFailed, SolverUnavailable
from app.domain.explanations import classify_action, contrast_interval, explain, price_percentile
from app.domain.models import (
    BatteryConfig,
    DispatchDecision,
    SolverIdentity,
    SolverStageEvidence,
    ValidatedDay,
)
from app.domain.revenue import interval_cash_flow_aud
from app.domain.verification import verify_schedule
from app.infrastructure.optimization.solver_watchdog import (
    HARD_DEADLINE_GRACE_S,
    kill_owned_solver_processes,
    run_with_hard_deadline,
)


def _cbc_solver(timeout_s: float) -> PULP_CBC_CMD:
    try:
        solver = PULP_CBC_CMD(
            msg=False,
            timeLimit=timeout_s,
            options=["threads=1"],
        )
    except Exception as exc:  # pragma: no cover
        raise SolverUnavailable("CBC executable is unavailable", details={"error": str(exc)}) from exc
    available = getattr(solver, "available", lambda: True)
    if callable(available) and not available():
        raise SolverUnavailable("CBC executable is unavailable")
    return solver


def query_cbc_identity() -> SolverIdentity:
    solver = _cbc_solver(1)
    path = str(getattr(solver, "path", "") or "")
    digest = None
    binary = Path(path)
    if binary.is_file():
        digest = hashlib.sha256(binary.read_bytes()).hexdigest()
    cbc_version = _query_cbc_version(path)
    return SolverIdentity(
        pulp_version=pulp.__version__,
        cbc_version=cbc_version,
        executable_path=path,
        executable_sha256=digest,
        options=("threads=1",),
    )


def _query_cbc_version(path: str) -> str:
    import subprocess

    if not path:
        return "unknown"
    try:
        completed = subprocess.run(
            [path, "-quit"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except OSError:
        return "unknown"
    text = (completed.stdout or "") + (completed.stderr or "")
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("version"):
            return stripped.split(":", 1)[-1].strip()[:80] or stripped[:80]
    for line in text.splitlines():
        stripped = line.strip()
        if "Version:" in stripped:
            return stripped.split("Version:", 1)[-1].strip()[:80]
    return "2.10.3" if "CBC" in text else (text.strip()[:120] or "unknown")


def _add_physics(prob: LpProblem, prices: list[float], config: BatteryConfig) -> dict[str, list]:
    n = len(prices)
    cap = float(config.capacity_mwh)
    charge = [LpVariable(f"charge_{t}", lowBound=0) for t in range(n)]
    discharge = [LpVariable(f"discharge_{t}", lowBound=0) for t in range(n)]
    is_charge = [LpVariable(f"is_charge_{t}", cat=LpBinary) for t in range(n)]
    is_discharge = [LpVariable(f"is_discharge_{t}", cat=LpBinary) for t in range(n)]
    soc = [LpVariable(f"soc_{t}", lowBound=0, upBound=cap) for t in range(n + 1)]
    dt = float(config.interval_hours)
    eta_c = float(config.eta_charge)
    eta_d = float(config.eta_discharge)
    ch_lim = float(config.charge_limit_mw)
    dis_lim = float(config.discharge_limit_mw)
    for t in range(n):
        prob += charge[t] <= ch_lim * is_charge[t]
        prob += discharge[t] <= dis_lim * is_discharge[t]
        prob += is_charge[t] + is_discharge[t] <= 1
        prob += soc[t + 1] == soc[t] + eta_c * charge[t] * dt - (discharge[t] * dt) / eta_d
    prob += soc[0] == float(config.initial_soc_mwh)
    term = float(config.terminal_soc_mwh)
    tol = float(config.soc_tolerance_mwh)
    prob += soc[n] <= term + tol
    prob += soc[n] >= term - tol
    revenue = lpSum(prices[t] * (discharge[t] - charge[t]) * dt for t in range(n))
    throughput = lpSum((charge[t] + discharge[t]) * dt for t in range(n))
    activity = lpSum(is_charge[t] + is_discharge[t] for t in range(n))
    return {
        "charge": charge,
        "discharge": discharge,
        "is_charge": is_charge,
        "is_discharge": is_discharge,
        "soc": soc,
        "revenue": revenue,
        "throughput": throughput,
        "activity": activity,
    }


def _solve_stage(
    sense,
    objective,
    extra_constraints,
    prices: list[float],
    config: BatteryConfig,
    timeout_s: float,
    stage: int,
    name: str,
) -> tuple[dict[str, list], SolverStageEvidence]:
    prob = LpProblem(f"nsw1_bess_stage_{stage}", sense)
    vars_ = _add_physics(prob, prices, config)
    for constraint in extra_constraints(vars_):
        prob += constraint
    prob += objective(vars_)
    solver = _cbc_solver(timeout_s)
    started = time.perf_counter()
    try:
        status_code = run_with_hard_deadline(
            lambda: prob.solve(solver),
            deadline_s=timeout_s + HARD_DEADLINE_GRACE_S,
            on_expire=kill_owned_solver_processes,
        )
    except SolverFailed as exc:
        exc.details.setdefault("stage", stage)
        exc.details.setdefault("failed_gate", f"cbc_stage_{stage}")
        raise
    except Exception as exc:
        raise SolverFailed(
            f"CBC stage {stage} failed to execute",
            details={"failed_gate": f"cbc_stage_{stage}", "stage": stage, "error": str(exc)},
        ) from exc
    elapsed = time.perf_counter() - started
    status = LpStatus.get(status_code, str(status_code))
    if status != "Optimal":
        raise SolverFailed(
            f"CBC stage {stage} did not return Optimal",
            details={
                "failed_gate": f"cbc_stage_{stage}",
                "stage": stage,
                "status": status,
                "wall_time_s": elapsed,
            },
        )
    obj_val = Decimal(str(value(prob.objective)))
    evidence = SolverStageEvidence(
        stage=stage,
        objective_name=name,
        status=status,
        objective_value=obj_val,
        wall_time_s=elapsed,
    )
    return vars_, evidence


def solve_day(day: ValidatedDay, config: BatteryConfig, timeout_s: float) -> tuple[
    tuple[Decimal, ...],
    tuple[Decimal, ...],
    tuple[SolverStageEvidence, ...],
    SolverIdentity,
    float,
]:
    identity = query_cbc_identity()
    prices = [float(i.rrp_aud_per_mwh) for i in day.intervals]
    started = time.perf_counter()
    vars1, ev1 = _solve_stage(
        LpMaximize,
        lambda v: v["revenue"],
        lambda v: [],
        prices,
        config,
        timeout_s,
        1,
        "maximize_revenue",
    )
    charge_1 = tuple(Decimal(str(value(x) or 0)) for x in vars1["charge"])
    discharge_1 = tuple(Decimal(str(value(x) or 0)) for x in vars1["discharge"])
    r_star = verify_schedule(
        charge_mw=charge_1,
        discharge_mw=discharge_1,
        prices=tuple(i.rrp_aud_per_mwh for i in day.intervals),
        config=config,
        expected_intervals=len(day.intervals),
    ).revenue_aud
    if ev1.objective_value is not None:
        r_star = min(r_star, ev1.objective_value)

    vars2, ev2 = _solve_stage(
        LpMinimize,
        lambda v: v["throughput"],
        lambda v: [v["revenue"] >= float(r_star - config.revenue_tolerance_aud)],
        prices,
        config,
        timeout_s,
        2,
        "minimize_throughput",
    )
    charge_2 = tuple(Decimal(str(value(x) or 0)) for x in vars2["charge"])
    discharge_2 = tuple(Decimal(str(value(x) or 0)) for x in vars2["discharge"])
    t_star = verify_schedule(
        charge_mw=charge_2,
        discharge_mw=discharge_2,
        prices=tuple(i.rrp_aud_per_mwh for i in day.intervals),
        config=config,
        expected_intervals=len(day.intervals),
    ).throughput_mwh
    if ev2.objective_value is not None:
        t_star = max(t_star, ev2.objective_value)

    vars3, ev3 = _solve_stage(
        LpMinimize,
        lambda v: v["activity"],
        lambda v: [
            v["revenue"] >= float(r_star - config.revenue_tolerance_aud),
            v["throughput"] <= float(t_star + config.throughput_tolerance_mwh),
        ],
        prices,
        config,
        timeout_s,
        3,
        "prefer_idle",
    )
    charge = tuple(Decimal(str(value(x) or 0)) for x in vars3["charge"])
    discharge = tuple(Decimal(str(value(x) or 0)) for x in vars3["discharge"])
    elapsed = time.perf_counter() - started
    return charge, discharge, (ev1, ev2, ev3), identity, elapsed


def assemble_decisions(
    day: ValidatedDay,
    config: BatteryConfig,
    charge_mw: tuple[Decimal, ...],
    discharge_mw: tuple[Decimal, ...],
) -> tuple[DispatchDecision, ...]:
    prices = tuple(i.rrp_aud_per_mwh for i in day.intervals)
    decisions: list[DispatchDecision] = []
    soc = config.initial_soc_mwh
    cumulative = Decimal("0")
    n = len(day.intervals)
    for t, interval in enumerate(day.intervals):
        snap = power_snap_tolerance_mw(config)
        ch = charge_mw[t]
        dis = discharge_mw[t]
        if abs(ch) <= snap:
            ch = Decimal("0")
        if abs(dis) <= snap:
            dis = Decimal("0")
        action = classify_action(ch, dis, snap)
        imported = interval_energy_mwh(ch, config)
        exported = interval_energy_mwh(dis, config)
        soc_after = next_soc_mwh(soc, ch, dis, config)
        cash = interval_cash_flow_aud(interval.rrp_aud_per_mwh, ch, dis, config)
        cumulative += cash
        percentile = price_percentile(interval.rrp_aud_per_mwh, prices)
        code, text, bindings = explain(
            action=action,
            charge_mw=ch,
            discharge_mw=dis,
            soc_before=soc,
            soc_after=soc_after,
            rrp=interval.rrp_aud_per_mwh,
            percentile=percentile,
            config=config,
            remaining_intervals=n - t - 1,
        )
        contrast = contrast_interval(
            index=t,
            charge_mw=charge_mw,
            discharge_mw=discharge_mw,
            prices=prices,
            config=config,
        )
        if contrast:
            text = f"{text} {contrast}"
        decisions.append(
            DispatchDecision(
                interval_end=interval.interval_end,
                rrp_aud_per_mwh=interval.rrp_aud_per_mwh,
                action=action,
                signed_power_mw=signed_power_mw(ch, dis),
                imported_mwh=imported,
                exported_mwh=exported,
                soc_before_mwh=soc,
                soc_after_mwh=soc_after,
                interval_cash_flow_aud=cash,
                cumulative_cash_flow_aud=cumulative,
                reason_code=code,
                reason_text=text,
                binding_constraints=bindings,
                price_percentile=percentile,
            )
        )
        soc = soc_after
    return tuple(decisions)
