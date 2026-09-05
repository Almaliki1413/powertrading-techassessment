from __future__ import annotations

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.api.problem_details import request_id_for
from app.application.run_benchmark import RunBenchmark
from app.domain.models import BatteryConfig, OptimizationResult

router = APIRouter()


class BatteryBody(BaseModel):
    capacity_mwh: Decimal = Decimal("200")
    charge_limit_mw: Decimal = Decimal("100")
    discharge_limit_mw: Decimal = Decimal("100")
    initial_soc_mwh: Decimal = Decimal("100")
    terminal_soc_mwh: Decimal = Decimal("100")
    round_trip_efficiency: Decimal = Decimal("0.9")


class OptimizationRequest(BaseModel):
    dataset_id: str
    selected_date: date
    mode: str = Field(default="independent_day")
    battery: BatteryBody = Field(default_factory=BatteryBody)


def _serialize(result: OptimizationResult) -> dict[str, object]:
    return {
        "request_id": result.request_id,
        "dataset_hash": result.dataset_hash,
        "config_hash": result.config_hash,
        "selected_date": result.selected_date.isoformat(),
        "benchmark_label": result.benchmark_label,
        "battery": result.battery.canonical_dict(),
        "solver": {
            "pulp_version": result.solver.pulp_version,
            "cbc_version": result.solver.cbc_version,
            "executable_path": result.solver.executable_path,
            "executable_sha256": result.solver.executable_sha256,
            "options": list(result.solver.options),
        },
        "stage_evidence": [
            {
                "stage": stage.stage,
                "objective_name": stage.objective_name,
                "status": stage.status,
                "objective_value": None if stage.objective_value is None else str(stage.objective_value),
                "wall_time_s": stage.wall_time_s,
            }
            for stage in result.stage_evidence
        ],
        "termination_status": result.termination_status,
        "metrics": {
            "gross_simulated_revenue_aud": str(result.total_revenue_aud),
            "imported_mwh": str(result.imported_mwh),
            "exported_mwh": str(result.exported_mwh),
            "throughput_mwh": str(result.total_throughput_mwh),
            "equivalent_full_cycles": str(result.equivalent_full_cycles),
            "ending_soc_mwh": str(result.ending_soc_mwh),
            "idle_preference_objective": str(result.idle_preference_objective),
            "solve_wall_time_s": result.solve_wall_time_s,
            "verification_passed": result.verification.passed,
        },
        "decisions": [
            {
                "interval_end": d.interval_end.isoformat(),
                "rrp_aud_per_mwh": str(d.rrp_aud_per_mwh),
                "action": d.action,
                "signed_power_mw": str(d.signed_power_mw),
                "imported_mwh": str(d.imported_mwh),
                "exported_mwh": str(d.exported_mwh),
                "soc_before_mwh": str(d.soc_before_mwh),
                "soc_after_mwh": str(d.soc_after_mwh),
                "interval_cash_flow_aud": str(d.interval_cash_flow_aud),
                "cumulative_cash_flow_aud": str(d.cumulative_cash_flow_aud),
                "reason_code": d.reason_code,
                "reason_text": d.reason_text,
                "binding_constraints": list(d.binding_constraints),
                "price_percentile": str(d.price_percentile),
            }
            for d in result.decisions
        ],
        "verification": {
            "passed": result.verification.passed,
            "failures": list(result.verification.failures),
        },
        "provenance": result.provenance,
    }


@router.post("/optimizations")
def run_optimization(body: OptimizationRequest, request: Request) -> dict[str, object]:
    runner: RunBenchmark = request.app.state.runner
    battery = BatteryConfig.from_round_trip(
        capacity_mwh=body.battery.capacity_mwh,
        charge_limit_mw=body.battery.charge_limit_mw,
        discharge_limit_mw=body.battery.discharge_limit_mw,
        initial_soc_mwh=body.battery.initial_soc_mwh,
        terminal_soc_mwh=body.battery.terminal_soc_mwh,
        round_trip_efficiency=body.battery.round_trip_efficiency,
    )
    result = runner.execute(
        request_id=request_id_for(request),
        dataset_id=body.dataset_id,
        selected_date=body.selected_date,
        mode=body.mode,
        battery=battery,
    )
    return _serialize(result)
