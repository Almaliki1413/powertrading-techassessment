"""Dynamic C/I/D DispatchIS parser. Maps DISPATCH/PRICE/5 by column name, never by index."""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from app import PARSER_VERSION, REGION_ID
from app.domain.errors import (
    AmbiguousRevision,
    IncompleteIntervalSet,
    InvalidRrp,
    MarketDataNotFirm,
    UnsupportedSchema,
)
from app.domain.models import DiscardedRecord, PriceInterval, QualityReport, QualityWarning, ValidatedDay
from app.infrastructure.aemo.zip_safety import (
    MAX_CSV_BYTES,
    MAX_NESTING_DEPTH,
    MAX_OUTER_MEMBERS_PER_DAY,
    iter_safe_members,
)

NEM_TZ = ZoneInfo("Australia/Brisbane")
REQUIRED_COLUMNS = (
    "SETTLEMENTDATE",
    "RUNNO",
    "REGIONID",
    "DISPATCHINTERVAL",
    "INTERVENTION",
    "RRP",
    "LASTCHANGED",
    "PRICE_STATUS",
    "MARKETSUSPENDEDFLAG",
)
AEMO_DT = "%Y/%m/%d %H:%M:%S"


@dataclass
class RawCandidate:
    settlementdate_raw: str
    interval_end: datetime
    run_no: int
    region_id: str
    dispatch_interval: str
    intervention: int
    rrp_raw: str
    rrp: Decimal
    last_changed: datetime
    last_changed_raw: str
    price_status: str
    market_suspended: bool
    source_archive: str
    source_outer_member: str
    source_csv: str
    source_record_number: int
    schema_version: int


@dataclass
class ParseStats:
    warnings: list[QualityWarning] = field(default_factory=list)
    discarded: list[DiscardedRecord] = field(default_factory=list)
    nsw1_candidates: int = 0
    malformed: int = 0
    irrelevant: int = 0
    duplicate_count: int = 0
    revision_count: int = 0


def parse_aemo_datetime(raw: str) -> datetime:
    return datetime.strptime(raw.strip(), AEMO_DT).replace(tzinfo=NEM_TZ)


def expected_interval_ends(selected: date) -> tuple[datetime, ...]:
    start = datetime.combine(selected, time(0, 5), tzinfo=NEM_TZ)
    return tuple(start + timedelta(minutes=5 * i) for i in range(288))


def _parse_bool_flag(raw: str) -> bool:
    value = raw.strip().upper()
    if value in {"1", "Y", "TRUE", "T"}:
        return True
    if value in {"0", "N", "FALSE", "F", ""}:
        return False
    raise ValueError(f"unrecognized flag {raw!r}")


def _parse_csv_rows(text: str, *, archive: str, outer: str, csv_name: str, stats: ParseStats) -> list[RawCandidate]:
    schema_by_key: dict[tuple[str, str, int], list[str]] = {}
    candidates: list[RawCandidate] = []
    reader = csv.reader(io.StringIO(text))
    for record_number, row in enumerate(reader, start=1):
        if not row:
            continue
        record_type = row[0].strip()
        if record_type == "C":
            continue
        if len(row) < 4:
            stats.malformed += 1
            stats.warnings.append(
                QualityWarning("MALFORMED_ROW", f"{outer}/{csv_name}#{record_number} too short", 1)
            )
            continue
        dataset, table, version_raw = row[1].strip(), row[2].strip(), row[3].strip()
        try:
            version = int(version_raw)
        except ValueError:
            stats.malformed += 1
            continue
        key = (dataset, table, version)
        if record_type == "I":
            columns = [c.strip() for c in row[4:]]
            existing = schema_by_key.get(key)
            if existing is not None and existing != columns:
                raise UnsupportedSchema(
                    "conflicting I-record schema",
                    details={"key": list(key), "outer": outer, "csv": csv_name},
                )
            schema_by_key[key] = columns
            continue
        if record_type == "D":
            columns = schema_by_key.get(key)
            if columns is None:
                if key == ("DISPATCH", "PRICE", 5):
                    raise UnsupportedSchema(
                        "PRICE data row without a matching I-record header",
                        details={"outer": outer, "csv": csv_name, "record": record_number},
                    )
                stats.irrelevant += 1
                continue
            values = row[4:]
            if len(values) != len(columns):
                if key == ("DISPATCH", "PRICE", 5):
                    raise UnsupportedSchema(
                        "PRICE row width does not match header",
                        details={
                            "outer": outer,
                            "expected": len(columns),
                            "actual": len(values),
                            "record": record_number,
                        },
                    )
                stats.malformed += 1
                continue
            if key != ("DISPATCH", "PRICE", 5):
                stats.irrelevant += 1
                continue
            missing = [c for c in REQUIRED_COLUMNS if c not in columns]
            if missing:
                raise UnsupportedSchema(
                    "required PRICE columns missing",
                    details={"missing": missing, "outer": outer},
                )
            mapped = dict(zip(columns, values, strict=True))
            region = mapped["REGIONID"].strip()
            if region != REGION_ID:
                continue
            stats.nsw1_candidates += 1
            rrp_raw = mapped["RRP"].strip()
            try:
                rrp = Decimal(rrp_raw)
            except InvalidOperation as exc:
                raise InvalidRrp(
                    "RRP is not numeric",
                    details={"rrp_raw": rrp_raw, "outer": outer, "record": record_number},
                ) from exc
            if not rrp.is_finite():
                raise InvalidRrp(
                    "RRP is NaN or infinite",
                    details={"rrp_raw": rrp_raw, "outer": outer, "record": record_number},
                )
            try:
                interval_end = parse_aemo_datetime(mapped["SETTLEMENTDATE"])
                last_changed = parse_aemo_datetime(mapped["LASTCHANGED"])
                market_suspended = _parse_bool_flag(mapped["MARKETSUSPENDEDFLAG"])
                run_no = int(mapped["RUNNO"].strip())
                intervention = int(mapped["INTERVENTION"].strip())
            except (ValueError, TypeError) as exc:
                raise UnsupportedSchema(
                    "PRICE field parse failure",
                    details={"outer": outer, "record": record_number, "error": str(exc)},
                ) from exc
            candidates.append(
                RawCandidate(
                    settlementdate_raw=mapped["SETTLEMENTDATE"].strip(),
                    interval_end=interval_end,
                    run_no=run_no,
                    region_id=REGION_ID,
                    dispatch_interval=mapped["DISPATCHINTERVAL"].strip(),
                    intervention=intervention,
                    rrp_raw=rrp_raw,
                    rrp=rrp,
                    last_changed=last_changed,
                    last_changed_raw=mapped["LASTCHANGED"].strip(),
                    price_status=mapped["PRICE_STATUS"].strip(),
                    market_suspended=market_suspended,
                    source_archive=archive,
                    source_outer_member=outer,
                    source_csv=csv_name,
                    source_record_number=record_number,
                    schema_version=version,
                )
            )
            continue
        stats.warnings.append(
            QualityWarning("UNKNOWN_RECORD_TYPE", f"{record_type} in {outer}/{csv_name}", 1)
        )
    return candidates


def parse_dispatchis_archive(data: bytes, *, filename: str) -> list[RawCandidate]:
    stats_holder: list[ParseStats] = []
    _candidates, _stats = parse_dispatchis_archive_with_stats(data, filename=filename)
    stats_holder.append(_stats)
    return _candidates


def parse_dispatchis_archive_with_stats(data: bytes, *, filename: str) -> tuple[list[RawCandidate], ParseStats]:
    stats = ParseStats()
    candidates: list[RawCandidate] = []
    budget = [0]
    outer_members = list(
        iter_safe_members(
            data,
            archive_label=filename,
            allowed_suffixes=(".zip",),
            max_members=MAX_OUTER_MEMBERS_PER_DAY,
            max_file_bytes=MAX_CSV_BYTES * 4,
            aggregate_budget=budget,
        )
    )
    for outer in sorted(outer_members, key=lambda m: m.name):
        nested = list(
            iter_safe_members(
                outer.data,
                archive_label=f"{filename}:{outer.name}",
                allowed_suffixes=(".csv", ".CSV"),
                max_members=16,
                max_file_bytes=MAX_CSV_BYTES,
                aggregate_budget=budget,
            )
        )
        if not nested:
            raise UnsupportedSchema(
                "nested ZIP contained no CSV",
                details={"outer": outer.name},
            )
        for csv_member in nested:
            try:
                text = csv_member.data.decode("utf-8-sig")
            except UnicodeDecodeError as exc:
                raise UnsupportedSchema(
                    "CSV is not UTF-8",
                    details={"outer": outer.name, "csv": csv_member.name},
                ) from exc
            candidates.extend(
                _parse_csv_rows(
                    text,
                    archive=filename,
                    outer=outer.name,
                    csv_name=csv_member.name,
                    stats=stats,
                )
            )
    if budget[0] == 0:
        raise UnsupportedSchema("archive produced no decompressed CSV bytes", details={"filename": filename})
    # nesting depth is structurally 2: outer zip -> inner zip -> csv
    _ = MAX_NESTING_DEPTH
    return candidates, stats


def _canonical_tuple(c: RawCandidate) -> tuple[object, ...]:
    return (
        c.settlementdate_raw,
        c.run_no,
        c.region_id,
        c.intervention,
        c.dispatch_interval,
        c.rrp_raw,
        c.price_status,
        c.market_suspended,
    )


def canonicalize_candidates(
    candidates: list[RawCandidate],
    stats: ParseStats,
) -> list[RawCandidate]:
    grouped: dict[tuple[object, ...], list[RawCandidate]] = defaultdict(list)
    for candidate in candidates:
        key = (
            "DISPATCH",
            "PRICE",
            5,
            candidate.settlementdate_raw,
            candidate.run_no,
            candidate.region_id,
            candidate.intervention,
        )
        grouped[key].append(candidate)

    selected: list[RawCandidate] = []
    for _key, rows in grouped.items():
        ranked = sorted(rows, key=lambda r: r.last_changed, reverse=True)
        top_time = ranked[0].last_changed
        top = [r for r in ranked if r.last_changed == top_time]
        if len(rows) > 1:
            stats.revision_count += len(rows) - 1
        if len(top) > 1:
            signatures = {_canonical_tuple(r) for r in top}
            if len(signatures) > 1:
                raise AmbiguousRevision(
                    "equally ranked LASTCHANGED records disagree",
                    details={"settlementdate": ranked[0].settlementdate_raw, "count": len(top)},
                )
            stats.duplicate_count += len(top) - 1
        winner = top[0]
        selected.append(winner)
        for loser in rows:
            if loser is winner:
                continue
            stats.discarded.append(
                DiscardedRecord(
                    settlementdate_raw=loser.settlementdate_raw,
                    last_changed_raw=loser.last_changed_raw,
                    reason="superseded_revision" if loser.last_changed != top_time else "duplicate",
                    source_outer_member=loser.source_outer_member,
                    source_record_number=loser.source_record_number,
                )
            )
    selected.sort(key=lambda c: c.interval_end)
    return selected


def to_price_interval(c: RawCandidate) -> PriceInterval:
    return PriceInterval(
        interval_end=c.interval_end,
        settlementdate_raw=c.settlementdate_raw,
        run_no=c.run_no,
        region_id="NSW1",
        dispatch_interval=c.dispatch_interval,
        intervention=c.intervention,
        rrp_aud_per_mwh=c.rrp,
        rrp_raw=c.rrp_raw,
        last_changed=c.last_changed,
        price_status=c.price_status,
        market_suspended=c.market_suspended,
        source_archive=c.source_archive,
        source_outer_member=c.source_outer_member,
        source_csv=c.source_csv,
        source_record_number=c.source_record_number,
        schema_dataset="DISPATCH",
        schema_table="PRICE",
        schema_version=c.schema_version,
    )


def validate_calendar_day(
    selected_date: date,
    intervals: list[PriceInterval],
    *,
    source_hashes: tuple[str, ...],
    stats: ParseStats,
    parser_version: str = PARSER_VERSION,
) -> ValidatedDay:
    expected = expected_interval_ends(selected_date)
    got = tuple(i.interval_end for i in intervals)
    if len(intervals) != 288 or got != expected:
        missing = [dt.isoformat() for dt in expected if dt not in set(got)]
        extras = [dt.isoformat() for dt in got if dt not in set(expected)]
        raise IncompleteIntervalSet(
            "selected day does not contain the exact 288 interval ends",
            details={
                "selected_date": selected_date.isoformat(),
                "count": len(intervals),
                "missing_interval_ends": missing[:12],
                "extra_interval_ends": extras[:12],
            },
        )
    for prev, cur in zip(intervals, intervals[1:], strict=False):
        if cur.interval_end <= prev.interval_end:
            raise IncompleteIntervalSet("timestamps are not strictly increasing")
        if cur.interval_end - prev.interval_end != timedelta(minutes=5):
            raise IncompleteIntervalSet("interval spacing is not five minutes")
        if cur.region_id != "NSW1":
            raise IncompleteIntervalSet("non-NSW1 record survived the filter")

    for interval in intervals:
        if interval.price_status.upper() != "FIRM" or interval.market_suspended or interval.intervention != 0:
            raise MarketDataNotFirm(
                "core policy requires FIRM, unsuspended, INTERVENTION=0 NSW1 prices",
                details={
                    "settlementdate": interval.settlementdate_raw,
                    "price_status": interval.price_status,
                    "market_suspended": interval.market_suspended,
                    "intervention": interval.intervention,
                },
            )

    dataset_hash = _dataset_hash(source_hashes, parser_version, selected_date, intervals)
    rrps = [i.rrp_aud_per_mwh for i in intervals]
    report = QualityReport(
        selected_date=selected_date,
        region_id="NSW1",
        interval_count=288,
        nsw1_candidate_count=stats.nsw1_candidates,
        discarded_count=len(stats.discarded),
        duplicate_count=stats.duplicate_count,
        revision_count=stats.revision_count,
        warning_count=len(stats.warnings) + stats.malformed + stats.irrelevant,
        warnings=tuple(stats.warnings),
        discarded=tuple(stats.discarded),
        rrp_min=min(rrps),
        rrp_max=max(rrps),
        first_interval_end=intervals[0].interval_end,
        last_interval_end=intervals[-1].interval_end,
        blocking=False,
        blocking_code=None,
        blocking_message=None,
        parser_version=parser_version,
        source_hashes=source_hashes,
    )
    return ValidatedDay(
        selected_date=selected_date,
        region_id="NSW1",
        intervals=tuple(intervals),
        source_hashes=source_hashes,
        dataset_hash=dataset_hash,
        quality_report=report,
    )


def _dataset_hash(
    source_hashes: tuple[str, ...],
    parser_version: str,
    selected_date: date,
    intervals: list[PriceInterval],
) -> str:
    import hashlib
    import json

    payload = {
        "source_hashes": list(source_hashes),
        "parser_version": parser_version,
        "region_id": "NSW1",
        "selected_date": selected_date.isoformat(),
        "interval_keys": [
            {
                "settlementdate": i.settlementdate_raw,
                "run_no": i.run_no,
                "intervention": i.intervention,
                "rrp_raw": i.rrp_raw,
            }
            for i in intervals
        ],
    }
    encoded = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()
