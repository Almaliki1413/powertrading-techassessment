from __future__ import annotations

from decimal import Decimal

from app.domain.explanations import contrast_interval
from app.domain.models import BatteryConfig


def test_charge_then_discharge_explains_why_not_idle() -> None:
    config = BatteryConfig()
    text = contrast_interval(
        index=0,
        charge_mw=(Decimal("100"), Decimal("0")),
        discharge_mw=(Decimal("0"), Decimal("100")),
        prices=(Decimal("10"), Decimal("80")),
        config=config,
    )
    assert "Idle" in text
    assert "later intervals held fixed" in text
    assert "infeasible" in text
    assert "terminal" in text.lower()


def test_idle_explains_why_not_charge_or_discharge() -> None:
    config = BatteryConfig()
    text = contrast_interval(
        index=0,
        charge_mw=(Decimal("0"), Decimal("0")),
        discharge_mw=(Decimal("0"), Decimal("0")),
        prices=(Decimal("50"), Decimal("50")),
        config=config,
    )
    assert "later intervals held fixed" in text
    assert "Charge" in text or "Discharge" in text
    assert "infeasible" in text or "revenue" in text


def test_assemble_decisions_appends_visible_contrast() -> None:
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    from app.domain.models import PriceInterval, QualityReport, ValidatedDay
    from app.infrastructure.optimization.pulp_cbc import assemble_decisions

    nem = ZoneInfo("Australia/Brisbane")
    start = datetime(2026, 8, 26, 0, 5, tzinfo=nem)
    prices = (Decimal("10"), Decimal("80"))
    intervals = []
    for i, rrp in enumerate(prices):
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
                source_archive="t.zip",
                source_outer_member="a.zip",
                source_csv="a.csv",
                source_record_number=i + 1,
                schema_dataset="DISPATCH",
                schema_table="PRICE",
                schema_version=5,
            )
        )
    day = ValidatedDay(
        selected_date=start.date(),
        region_id="NSW1",
        intervals=tuple(intervals),
        source_hashes=("t",),
        dataset_hash="sha256:t",
        quality_report=QualityReport(
            selected_date=start.date(),
            region_id="NSW1",
            interval_count=2,
            nsw1_candidate_count=2,
            discarded_count=0,
            duplicate_count=0,
            revision_count=0,
            warning_count=0,
            warnings=(),
            discarded=(),
            rrp_min=Decimal("10"),
            rrp_max=Decimal("80"),
            first_interval_end=intervals[0].interval_end,
            last_interval_end=intervals[1].interval_end,
            blocking=False,
            blocking_code=None,
            blocking_message=None,
            parser_version="1.0.0",
            source_hashes=("t",),
        ),
    )
    decisions = assemble_decisions(
        day,
        BatteryConfig(),
        (Decimal("100"), Decimal("0")),
        (Decimal("0"), Decimal("100")),
    )
    assert "Idle" in decisions[0].reason_text
    assert "later intervals held fixed" in decisions[0].reason_text
