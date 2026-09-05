from __future__ import annotations

from pathlib import Path

import pytest

PINNED = Path(__file__).resolve().parents[3] / "data" / "pinned" / "PUBLIC_DISPATCHIS_20260826.zip"


@pytest.mark.skipif(not PINNED.is_file(), reason="inspected archive not present")
def test_inspected_day_has_288_nsw1_rows() -> None:
    from datetime import date

    from app.infrastructure.aemo.dispatchis_parser import (
        canonicalize_candidates,
        parse_dispatchis_archive_with_stats,
        to_price_interval,
        validate_calendar_day,
    )

    data = PINNED.read_bytes()
    candidates, stats = parse_dispatchis_archive_with_stats(data, filename=PINNED.name)
    selected = canonicalize_candidates(candidates, stats)
    intervals = [to_price_interval(c) for c in selected]
    day = validate_calendar_day(
        date(2026, 8, 26),
        intervals,
        source_hashes=("f9f389839f2ea704770fa736ef85e014a2cc5ab2ef5f4dcb363e70d1f70d22fb",),
        stats=stats,
    )
    assert len(day.intervals) == 288
    assert day.quality_report.rrp_min == day.quality_report.rrp_min
    rrps = [i.rrp_aud_per_mwh for i in day.intervals]
    assert min(rrps) == day.quality_report.rrp_min
    assert float(min(rrps)) == -2.0
    assert float(max(rrps)) == pytest.approx(161.21945)
