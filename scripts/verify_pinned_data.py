#!/usr/bin/env python3
"""Re-run archive integrity, parser, completeness, and provenance checks."""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.application.manifest import load_manifest  # noqa: E402
from app.domain.errors import DomainError  # noqa: E402
from app.infrastructure.aemo.dispatchis_parser import (  # noqa: E402
    canonicalize_candidates,
    parse_dispatchis_archive_with_stats,
    to_price_interval,
    validate_calendar_day,
)


def main() -> int:
    manifest = load_manifest(ROOT / "data" / "pinned" / "manifest.json")
    failures = 0
    for item in manifest.files:
        path = ROOT / "data" / "pinned" / item.filename
        print(f"== {item.dispatch_date.isoformat()} {item.filename} [{item.inspection_status}]")
        if item.inspection_status != "passed":
            print("  skipped: unverified (release blocker until inspection passes)")
            continue
        if not path.is_file():
            print("  FAIL missing file")
            failures += 1
            continue
        data = path.read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        if item.sha256 and digest != item.sha256:
            print(f"  FAIL hash {digest} != {item.sha256}")
            failures += 1
            continue
        if item.listing_size_bytes is not None and len(data) != item.listing_size_bytes:
            print(f"  FAIL size {len(data)} != {item.listing_size_bytes}")
            failures += 1
            continue
        try:
            candidates, stats = parse_dispatchis_archive_with_stats(data, filename=item.filename)
            selected = canonicalize_candidates(candidates, stats)
            intervals = [to_price_interval(c) for c in selected]
            day = validate_calendar_day(
                item.dispatch_date,
                intervals,
                source_hashes=(digest,),
                stats=stats,
            )
        except DomainError as exc:
            print(f"  FAIL {exc.code}: {exc.message}")
            failures += 1
            continue
        print(
            f"  PASS intervals={day.quality_report.interval_count} "
            f"rrp=[{day.quality_report.rrp_min}, {day.quality_report.rrp_max}] "
            f"hash={digest}"
        )
    if failures:
        print(f"{failures} blocking failure(s)")
        return 1
    print("verify-data ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
