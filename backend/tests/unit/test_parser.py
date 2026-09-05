from __future__ import annotations

import io
import zipfile
from datetime import date
from decimal import Decimal

import pytest

from app.domain.errors import IncompleteIntervalSet, InvalidRrp, UnsupportedSchema
from app.infrastructure.aemo.dispatchis_parser import (
    canonicalize_candidates,
    parse_dispatchis_archive_with_stats,
    to_price_interval,
    validate_calendar_day,
)


def _csv(rows: list[list[str]]) -> str:
    return "\n".join(",".join(row) for row in rows) + "\n"


def _nested_zip(csv_name: str, csv_text: str) -> bytes:
    inner = io.BytesIO()
    with zipfile.ZipFile(inner, "w") as zf:
        zf.writestr(csv_name, csv_text.encode("utf-8"))
    outer = io.BytesIO()
    with zipfile.ZipFile(outer, "w") as zf:
        zf.writestr("PUBLIC_DISPATCHIS_202608260005_0000000312345678.zip", inner.getvalue())
    return outer.getvalue()


HEADER = [
    "I",
    "DISPATCH",
    "PRICE",
    "5",
    "SETTLEMENTDATE",
    "RUNNO",
    "REGIONID",
    "DISPATCHINTERVAL",
    "INTERVENTION",
    "RRP",
    "LASTCHANGED",
    "PRICE_STATUS",
    "MARKETSUSPENDEDFLAG",
]


def _row(settlement: str, region: str, rrp: str, last_changed: str, dispatch_interval: str = "202608260405") -> list[str]:
    return [
        "D",
        "DISPATCH",
        "PRICE",
        "5",
        settlement,
        "1",
        region,
        dispatch_interval,
        "0",
        rrp,
        last_changed,
        "FIRM",
        "0",
    ]


def test_named_column_mapping_and_nsw1_filter() -> None:
    csv_text = _csv(
        [
            ["C", "DISPATCHIS", "AEMO", "PREDISPATCH"],
            HEADER,
            _row("2026/08/26 00:05:00", "NSW1", "12.5", "2026/08/26 00:05:01"),
            _row("2026/08/26 00:05:00", "VIC1", "99", "2026/08/26 00:05:01"),
        ]
    )
    data = _nested_zip("x.csv", csv_text)
    candidates, stats = parse_dispatchis_archive_with_stats(data, filename="PUBLIC_DISPATCHIS_20260826.zip")
    assert stats.nsw1_candidates == 1
    assert len(candidates) == 1
    assert candidates[0].rrp == Decimal("12.5")


def test_missing_required_column_rejected() -> None:
    header = HEADER[:-1]
    row = _row("2026/08/26 00:05:00", "NSW1", "1", "2026/08/26 00:05:01")[:-1]
    data = _nested_zip("x.csv", _csv([header, row]))
    with pytest.raises(UnsupportedSchema):
        parse_dispatchis_archive_with_stats(data, filename="f.zip")


def test_invalid_rrp_rejected() -> None:
    data = _nested_zip(
        "x.csv",
        _csv([HEADER, _row("2026/08/26 00:05:00", "NSW1", "NaN", "2026/08/26 00:05:01")]),
    )
    with pytest.raises(InvalidRrp):
        parse_dispatchis_archive_with_stats(data, filename="f.zip")


def test_revision_keeps_greatest_lastchanged() -> None:
    csv_text = _csv(
        [
            HEADER,
            _row("2026/08/26 00:05:00", "NSW1", "1.0", "2026/08/26 00:05:01"),
            _row("2026/08/26 00:05:00", "NSW1", "2.0", "2026/08/26 00:06:01"),
        ]
    )
    candidates, stats = parse_dispatchis_archive_with_stats(
        _nested_zip("x.csv", csv_text), filename="f.zip"
    )
    selected = canonicalize_candidates(candidates, stats)
    assert len(selected) == 1
    assert selected[0].rrp == Decimal("2.0")
    assert stats.revision_count == 1


def test_dispatchinterval_reset_does_not_split_day() -> None:
    csv_text = _csv(
        [
            HEADER,
            _row("2026/08/26 04:00:00", "NSW1", "1", "2026/08/26 04:00:01", "202608260400"),
            _row("2026/08/26 04:05:00", "NSW1", "1", "2026/08/26 04:05:01", "202608270405"),
        ]
    )
    candidates, stats = parse_dispatchis_archive_with_stats(
        _nested_zip("x.csv", csv_text), filename="f.zip"
    )
    selected = canonicalize_candidates(candidates, stats)
    assert [c.interval_end.hour for c in selected] == [4, 4]
    assert selected[0].dispatch_interval.startswith("20260826")
    assert selected[1].dispatch_interval.startswith("20260827")


def test_incomplete_day_is_blocking() -> None:
    csv_text = _csv([HEADER, _row("2026/08/26 00:05:00", "NSW1", "1", "2026/08/26 00:05:01")])
    candidates, stats = parse_dispatchis_archive_with_stats(
        _nested_zip("x.csv", csv_text), filename="f.zip"
    )
    intervals = [to_price_interval(c) for c in canonicalize_candidates(candidates, stats)]
    with pytest.raises(IncompleteIntervalSet):
        validate_calendar_day(date(2026, 8, 26), intervals, source_hashes=("abc",), stats=stats)
