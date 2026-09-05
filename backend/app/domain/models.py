"""Immutable domain value objects. Pydantic stays at the API/config boundary."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from app.domain.errors import InvalidConfiguration

ReasonCode = Literal[
    "BOUND_SOC_MIN",
    "BOUND_SOC_MAX",
    "BOUND_POWER",
    "TERMINAL_TARGET",
    "ECONOMIC_CHARGE",
    "ECONOMIC_DISCHARGE",
    "IDLE_TIE_BREAK",
    "IDLE_GLOBAL_OPTIMUM",
]

Action = Literal["charge", "discharge", "idle"]
NEM_TZ_NAME = "Australia/Brisbane"


@dataclass(frozen=True, slots=True)
class PriceInterval:
    interval_end: datetime
    settlementdate_raw: str
    run_no: int
    region_id: Literal["NSW1"]
    dispatch_interval: str
    intervention: int
    rrp_aud_per_mwh: Decimal
    rrp_raw: str
    last_changed: datetime
    price_status: str
    market_suspended: bool
    source_archive: str
    source_outer_member: str
    source_csv: str
    source_record_number: int
    schema_dataset: Literal["DISPATCH"]
    schema_table: Literal["PRICE"]
    schema_version: int


@dataclass(frozen=True, slots=True)
class QualityWarning:
    code: str
    message: str
    count: int = 1


@dataclass(frozen=True, slots=True)
class DiscardedRecord:
    settlementdate_raw: str
    last_changed_raw: str
    reason: str
    source_outer_member: str
    source_record_number: int


@dataclass(frozen=True, slots=True)
class QualityReport:
    selected_date: date
    region_id: str
    interval_count: int
    nsw1_candidate_count: int
    discarded_count: int
    duplicate_count: int
    revision_count: int
    warning_count: int
    warnings: tuple[QualityWarning, ...]
    discarded: tuple[DiscardedRecord, ...]
    rrp_min: Decimal | None
    rrp_max: Decimal | None
    first_interval_end: datetime | None
    last_interval_end: datetime | None
    blocking: bool
    blocking_code: str | None
    blocking_message: str | None
    parser_version: str
    source_hashes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ValidatedDay:
    selected_date: date
    region_id: Literal["NSW1"]
    intervals: tuple[PriceInterval, ...]
    source_hashes: tuple[str, ...]
    dataset_hash: str
    quality_report: QualityReport


@dataclass(frozen=True, slots=True)
class BatteryConfig:
    capacity_mwh: Decimal = Decimal("200")
    charge_limit_mw: Decimal = Decimal("100")
    discharge_limit_mw: Decimal = Decimal("100")
    initial_soc_mwh: Decimal = Decimal("100")
    terminal_soc_mwh: Decimal = Decimal("100")
    eta_charge: Decimal = Decimal("0.90").sqrt()
    eta_discharge: Decimal = Decimal("0.90").sqrt()
    interval_hours: Decimal = Decimal(5) / Decimal(60)
    soc_tolerance_mwh: Decimal = Decimal("0.000001")
    revenue_tolerance_aud: Decimal = Decimal("0.000001")
    throughput_tolerance_mwh: Decimal = Decimal("0.000001")

    def __post_init__(self) -> None:
        errors: list[str] = []
        if self.capacity_mwh <= 0:
            errors.append("capacity_mwh must be positive")
        if self.charge_limit_mw <= 0 or self.discharge_limit_mw <= 0:
            errors.append("charge and discharge limits must be positive")
        if not (Decimal("0") < self.eta_charge <= Decimal("1")):
            errors.append("eta_charge must be in (0, 1]")
        if not (Decimal("0") < self.eta_discharge <= Decimal("1")):
            errors.append("eta_discharge must be in (0, 1]")
        if not (Decimal("0") <= self.initial_soc_mwh <= self.capacity_mwh):
            errors.append("initial_soc_mwh must be inside [0, capacity]")
        if not (Decimal("0") <= self.terminal_soc_mwh <= self.capacity_mwh):
            errors.append("terminal_soc_mwh must be inside [0, capacity]")
        if self.interval_hours <= 0:
            errors.append("interval_hours must be positive")
        if errors:
            raise InvalidConfiguration("; ".join(errors), details={"errors": errors})

    @classmethod
    def from_round_trip(
        cls,
        *,
        capacity_mwh: Decimal = Decimal("200"),
        charge_limit_mw: Decimal = Decimal("100"),
        discharge_limit_mw: Decimal = Decimal("100"),
        initial_soc_mwh: Decimal = Decimal("100"),
        terminal_soc_mwh: Decimal = Decimal("100"),
        round_trip_efficiency: Decimal = Decimal("0.9"),
    ) -> BatteryConfig:
        if not (Decimal("0") < round_trip_efficiency <= Decimal("1")):
            raise InvalidConfiguration(
                "round_trip_efficiency must be in (0, 1]",
                details={"round_trip_efficiency": str(round_trip_efficiency)},
            )
        eta = round_trip_efficiency.sqrt()
        return cls(
            capacity_mwh=capacity_mwh,
            charge_limit_mw=charge_limit_mw,
            discharge_limit_mw=discharge_limit_mw,
            initial_soc_mwh=initial_soc_mwh,
            terminal_soc_mwh=terminal_soc_mwh,
            eta_charge=eta,
            eta_discharge=eta,
        )

    def canonical_dict(self) -> dict[str, str]:
        return {
            "capacity_mwh": str(self.capacity_mwh),
            "charge_limit_mw": str(self.charge_limit_mw),
            "discharge_limit_mw": str(self.discharge_limit_mw),
            "initial_soc_mwh": str(self.initial_soc_mwh),
            "terminal_soc_mwh": str(self.terminal_soc_mwh),
            "eta_charge": str(self.eta_charge),
            "eta_discharge": str(self.eta_discharge),
            "interval_hours": str(self.interval_hours),
            "soc_tolerance_mwh": str(self.soc_tolerance_mwh),
            "revenue_tolerance_aud": str(self.revenue_tolerance_aud),
            "throughput_tolerance_mwh": str(self.throughput_tolerance_mwh),
        }


@dataclass(frozen=True, slots=True)
class DispatchDecision:
    interval_end: datetime
    rrp_aud_per_mwh: Decimal
    action: Action
    signed_power_mw: Decimal
    imported_mwh: Decimal
    exported_mwh: Decimal
    soc_before_mwh: Decimal
    soc_after_mwh: Decimal
    interval_cash_flow_aud: Decimal
    cumulative_cash_flow_aud: Decimal
    reason_code: ReasonCode
    reason_text: str
    binding_constraints: tuple[str, ...]
    price_percentile: Decimal


@dataclass(frozen=True, slots=True)
class VerificationReport:
    passed: bool
    interval_count: int
    revenue_aud: Decimal
    throughput_mwh: Decimal
    imported_mwh: Decimal
    exported_mwh: Decimal
    ending_soc_mwh: Decimal
    equivalent_full_cycles: Decimal
    failures: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SolverStageEvidence:
    stage: int
    objective_name: str
    status: str
    objective_value: Decimal | None
    wall_time_s: float
    solver_log: str | None = None


@dataclass(frozen=True, slots=True)
class SolverIdentity:
    pulp_version: str
    cbc_version: str
    executable_path: str
    executable_sha256: str | None
    options: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class OptimizationResult:
    request_id: str
    dataset_hash: str
    config_hash: str
    selected_date: date
    benchmark_label: str
    battery: BatteryConfig
    solver: SolverIdentity
    stage_evidence: tuple[SolverStageEvidence, ...]
    termination_status: str
    total_revenue_aud: Decimal
    total_throughput_mwh: Decimal
    idle_preference_objective: Decimal
    imported_mwh: Decimal
    exported_mwh: Decimal
    ending_soc_mwh: Decimal
    equivalent_full_cycles: Decimal
    solve_wall_time_s: float
    decisions: tuple[DispatchDecision, ...]
    verification: VerificationReport
    quality_report: QualityReport
    provenance: dict[str, object] = field(default_factory=dict)
