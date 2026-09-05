from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.domain.models import BatteryConfig, PriceInterval, QualityReport, ValidatedDay
from app.domain.verification import verify_schedule
from app.infrastructure.optimization.pulp_cbc import solve_day

NEM = ZoneInfo("Australia/Brisbane")


def _day(prices: list[Decimal]) -> ValidatedDay:
    intervals = []
    start = datetime(2026, 8, 26, 0, 5, tzinfo=NEM)
    for i, rrp in enumerate(prices):
        end = start.replace() if i == 0 else start
        from datetime import timedelta

        end = start + timedelta(minutes=5 * i)
        intervals.append(
            PriceInterval(
                interval_end=end,
                settlementdate_raw=end.strftime("%Y/%m/%d %H:%M:%S"),
                run_no=1,
                region_id="NSW1",
                dispatch_interval="x",
                intervention=0,
                rrp_aud_per_mwh=rrp,
                rrp_raw=str(rrp),
                last_changed=end,
                price_status="FIRM",
                market_suspended=False,
                source_archive="test.zip",
                source_outer_member="a.zip",
                source_csv="a.csv",
                source_record_number=i + 1,
                schema_dataset="DISPATCH",
                schema_table="PRICE",
                schema_version=5,
            )
        )
    report = QualityReport(
        selected_date=start.date(),
        region_id="NSW1",
        interval_count=len(intervals),
        nsw1_candidate_count=len(intervals),
        discarded_count=0,
        duplicate_count=0,
        revision_count=0,
        warning_count=0,
        warnings=(),
        discarded=(),
        rrp_min=min(prices),
        rrp_max=max(prices),
        first_interval_end=intervals[0].interval_end,
        last_interval_end=intervals[-1].interval_end,
        blocking=False,
        blocking_code=None,
        blocking_message=None,
        parser_version="1.0.0",
        source_hashes=("test",),
    )
    return ValidatedDay(
        selected_date=start.date(),
        region_id="NSW1",
        intervals=tuple(intervals),
        source_hashes=("test",),
        dataset_hash="sha256:test",
        quality_report=report,
    )


def test_six_interval_profitable_spread() -> None:
    prices = [Decimal("10"), Decimal("10"), Decimal("10"), Decimal("200"), Decimal("200"), Decimal("200")]
    day = _day(prices)
    config = BatteryConfig()
    charge, discharge, stages, _identity, _elapsed = solve_day(day, config, timeout_s=15)
    report = verify_schedule(
        charge_mw=charge,
        discharge_mw=discharge,
        prices=tuple(prices),
        config=config,
        expected_intervals=6,
    )
    assert report.passed
    assert report.revenue_aud > 0
    assert all(stage.status == "Optimal" for stage in stages)
    assert sum(discharge[3:]) > sum(discharge[:3])


def test_flat_price_resolves_to_idle() -> None:
    prices = [Decimal("50")] * 6
    day = _day(prices)
    config = BatteryConfig()
    charge, discharge, stages, *_ = solve_day(day, config, timeout_s=15)
    report = verify_schedule(
        charge_mw=charge,
        discharge_mw=discharge,
        prices=tuple(prices),
        config=config,
        expected_intervals=6,
    )
    assert report.passed
    assert report.throughput_mwh <= config.throughput_tolerance_mwh
    assert stages[2].status == "Optimal"


def test_negative_price_prefers_charging() -> None:
    prices = [Decimal("-20"), Decimal("-20"), Decimal("-20"), Decimal("80"), Decimal("80"), Decimal("80")]
    day = _day(prices)
    config = BatteryConfig()
    charge, discharge, *_ = solve_day(day, config, timeout_s=15)
    assert sum(charge[:3]) > 0
    assert sum(discharge[3:]) > 0


def test_verifier_detects_corrupted_schedule() -> None:
    prices = [Decimal("10")] * 6
    config = BatteryConfig()
    report = verify_schedule(
        charge_mw=(Decimal("100"),) * 6,
        discharge_mw=(Decimal("100"),) * 6,
        prices=tuple(prices),
        config=config,
        expected_intervals=6,
    )
    assert report.passed is False
