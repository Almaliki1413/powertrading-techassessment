"""RunBenchmark: semaphore, cache, three-stage solve, independent verify, reasons."""

from __future__ import annotations

import threading
from datetime import date
from decimal import Decimal

from app import BENCHMARK_LABEL
from app.application.validate_day import ValidateDay
from app.domain.errors import InvalidConfiguration, PostSolveVerificationFailed, SolverBusy
from app.domain.models import BatteryConfig, OptimizationResult
from app.infrastructure.optimization.pulp_cbc import assemble_decisions, solve_day
from app.infrastructure.storage.content_cache import sha256_json
from app.settings import Settings


class RunBenchmark:
    def __init__(self, settings: Settings, validate_day: ValidateDay) -> None:
        self.settings = settings
        self.validate_day = validate_day
        self._semaphore = threading.Semaphore(settings.max_concurrent_solves)

    def execute(
        self,
        *,
        request_id: str,
        dataset_id: str,
        selected_date: date,
        mode: str,
        battery: BatteryConfig,
    ) -> OptimizationResult:
        if mode != "independent_day":
            raise InvalidConfiguration("only independent_day mode is supported")
        day = self.validate_day.execute(dataset_id, selected_date)
        config_hash = "sha256:" + sha256_json(battery.canonical_dict())
        acquired = self._semaphore.acquire(timeout=self.settings.queue_timeout_s)
        if not acquired:
            raise SolverBusy(
                "solver queue timed out; retry shortly",
                details={"queue_timeout_s": self.settings.queue_timeout_s},
            )
        try:
            charge, discharge, stages, identity, elapsed = solve_day(
                day, battery, self.settings.solver_timeout_s
            )
            prices = tuple(item.rrp_aud_per_mwh for item in day.intervals)
            from app.domain.verification import verify_schedule

            verification = verify_schedule(
                charge_mw=charge,
                discharge_mw=discharge,
                prices=prices,
                config=battery,
                expected_intervals=len(day.intervals),
            )
            if not verification.passed:
                raise PostSolveVerificationFailed(
                    "independent verifier rejected the CBC schedule",
                    details={"failures": list(verification.failures)},
                )
            decisions = assemble_decisions(day, battery, charge, discharge)
            idle_obj = Decimal(str(stages[2].objective_value or 0))
            return OptimizationResult(
                request_id=request_id,
                dataset_hash=day.dataset_hash,
                config_hash=config_hash,
                selected_date=selected_date,
                benchmark_label=BENCHMARK_LABEL,
                battery=battery,
                solver=identity,
                stage_evidence=stages,
                termination_status="Optimal",
                total_revenue_aud=verification.revenue_aud,
                total_throughput_mwh=verification.throughput_mwh,
                idle_preference_objective=idle_obj,
                imported_mwh=verification.imported_mwh,
                exported_mwh=verification.exported_mwh,
                ending_soc_mwh=verification.ending_soc_mwh,
                equivalent_full_cycles=verification.equivalent_full_cycles,
                solve_wall_time_s=elapsed,
                decisions=decisions,
                verification=verification,
                quality_report=day.quality_report,
                provenance={
                    "dataset_id": dataset_id,
                    "source_hashes": list(day.source_hashes),
                    "parser_version": day.quality_report.parser_version,
                    "interval_count": len(day.intervals),
                    "mode": mode,
                },
            )
        finally:
            self._semaphore.release()
