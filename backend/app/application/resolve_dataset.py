"""ResolveDataset: archive resolution, parse, canonicalize, cache, quality reporting."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from app import PARSER_VERSION, REGION_ID
from app.application.manifest import PinnedManifest, load_manifest
from app.domain.errors import ArchiveNotFound, DomainError, HashMismatch, InvalidDateRange
from app.domain.models import QualityReport, ValidatedDay
from app.infrastructure.aemo.archive_client import ArchiveClient, archive_filename, validate_range
from app.infrastructure.aemo.dispatchis_parser import (
    canonicalize_candidates,
    parse_dispatchis_archive_with_stats,
    to_price_interval,
    validate_calendar_day,
)
from app.infrastructure.storage.content_cache import ContentCache, sha256_json
from app.settings import Settings


@dataclass(frozen=True, slots=True)
class DaySummary:
    date: date
    status: str
    selectable: bool
    interval_count: int | None
    rrp_min: str | None
    rrp_max: str | None
    blocking_code: str | None
    blocking_message: str | None
    source_hash: str | None
    inspection_status: str


@dataclass(frozen=True, slots=True)
class DatasetReference:
    dataset_id: str
    start_date: date
    end_date: date
    source_mode: str
    region_id: str
    days: tuple[DaySummary, ...]
    validated: dict[date, ValidatedDay]


class ResolveDataset:
    def __init__(self, settings: Settings, cache: ContentCache, client: ArchiveClient) -> None:
        self.settings = settings
        self.cache = cache
        self.client = client
        self._store: dict[str, DatasetReference] = {}

    def execute(self, start_date: date, end_date: date, source_mode: str) -> DatasetReference:
        days = validate_range(start_date, end_date, self.settings.max_range_days)
        mode = source_mode or self.settings.source_mode
        if mode not in {"pinned", "archive_refresh"}:
            raise InvalidDateRange("source_mode must be pinned or archive_refresh")
        manifest = load_manifest(self.settings.manifest_path)
        summaries: list[DaySummary] = []
        validated: dict[date, ValidatedDay] = {}
        hashes: list[str] = []
        for day in days:
            summary, maybe_day, digest = self._resolve_day(day, mode, manifest)
            summaries.append(summary)
            if maybe_day is not None:
                validated[day] = maybe_day
                hashes.append(maybe_day.dataset_hash)
            elif digest:
                hashes.append(digest)
        dataset_id = "sha256:" + sha256_json(
            {
                "start": start_date.isoformat(),
                "end": end_date.isoformat(),
                "mode": mode,
                "parser": PARSER_VERSION,
                "hashes": hashes,
            }
        )
        reference = DatasetReference(
            dataset_id=dataset_id,
            start_date=start_date,
            end_date=end_date,
            source_mode=mode,
            region_id=REGION_ID,
            days=tuple(summaries),
            validated=validated,
        )
        self._store[dataset_id] = reference
        return reference

    def get(self, dataset_id: str) -> DatasetReference:
        ref = self._store.get(dataset_id)
        if ref is None:
            raise ArchiveNotFound("unknown dataset id", details={"dataset_id": dataset_id})
        return ref

    def _resolve_day(
        self,
        day: date,
        mode: str,
        manifest: PinnedManifest,
    ) -> tuple[DaySummary, ValidatedDay | None, str | None]:
        pinned = None
        try:
            pinned = manifest.file_for(day)
        except ArchiveNotFound:
            if mode == "pinned":
                return (
                    DaySummary(
                        date=day,
                        status="missing",
                        selectable=False,
                        interval_count=None,
                        rrp_min=None,
                        rrp_max=None,
                        blocking_code="ARCHIVE_NOT_FOUND",
                        blocking_message=f"no pinned archive for {day.isoformat()}",
                        source_hash=None,
                        inspection_status="missing",
                    ),
                    None,
                    None,
                )
        try:
            if mode == "pinned":
                assert pinned is not None
                if not pinned.sha256:
                    raise HashMismatch(
                        "pinned hash is absent — release blocker, not a warning",
                        details={"date": day.isoformat()},
                    )
                data, digest = self.client.load_pinned(day, pinned.sha256, pinned.listing_size_bytes)
            else:
                data, digest = self.client.download(day)
            candidates, stats = parse_dispatchis_archive_with_stats(data, filename=archive_filename(day))
            selected = canonicalize_candidates(candidates, stats)
            intervals = [to_price_interval(c) for c in selected]
            validated = validate_calendar_day(
                day,
                intervals,
                source_hashes=(digest,),
                stats=stats,
            )
            report = validated.quality_report
            return (
                DaySummary(
                    date=day,
                    status="validated",
                    selectable=True,
                    interval_count=report.interval_count,
                    rrp_min=str(report.rrp_min) if report.rrp_min is not None else None,
                    rrp_max=str(report.rrp_max) if report.rrp_max is not None else None,
                    blocking_code=None,
                    blocking_message=None,
                    source_hash=digest,
                    inspection_status=pinned.inspection_status if pinned else "refresh",
                ),
                validated,
                digest,
            )
        except DomainError as exc:
            return (
                DaySummary(
                    date=day,
                    status="blocking",
                    selectable=False,
                    interval_count=None,
                    rrp_min=None,
                    rrp_max=None,
                    blocking_code=exc.code,
                    blocking_message=exc.message,
                    source_hash=None,
                    inspection_status=pinned.inspection_status if pinned else "failed",
                ),
                None,
                None,
            )


def quality_to_dict(report: QualityReport) -> dict[str, object]:
    return {
        "selected_date": report.selected_date.isoformat(),
        "region_id": report.region_id,
        "interval_count": report.interval_count,
        "nsw1_candidate_count": report.nsw1_candidate_count,
        "discarded_count": report.discarded_count,
        "duplicate_count": report.duplicate_count,
        "revision_count": report.revision_count,
        "warning_count": report.warning_count,
        "rrp_min": str(report.rrp_min) if report.rrp_min is not None else None,
        "rrp_max": str(report.rrp_max) if report.rrp_max is not None else None,
        "blocking": report.blocking,
        "parser_version": report.parser_version,
        "source_hashes": list(report.source_hashes),
    }
