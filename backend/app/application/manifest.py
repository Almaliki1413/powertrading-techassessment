"""Load and verify the committed pinned-data manifest."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from app.domain.errors import ArchiveNotFound, HashMismatch, InvalidConfiguration


@dataclass(frozen=True, slots=True)
class PinnedFile:
    dispatch_date: date
    filename: str
    url: str
    listing_size_bytes: int | None
    sha256: str | None
    inspection_status: str


@dataclass(frozen=True, slots=True)
class PinnedManifest:
    schema_version: int
    region_id: str
    start_date: date
    end_date: date
    default_date: date
    source_base_url: str
    files: tuple[PinnedFile, ...]
    retrieved_at_utc: str | None
    validator_version: str | None

    def file_for(self, day: date) -> PinnedFile:
        for item in self.files:
            if item.dispatch_date == day:
                return item
        raise ArchiveNotFound(f"manifest has no entry for {day.isoformat()}")

    def approved_default(self) -> date:
        default_file = self.file_for(self.default_date)
        if default_file.inspection_status == "passed" and default_file.sha256:
            return self.default_date
        for item in self.files:
            if item.inspection_status == "passed" and item.sha256:
                return item.dispatch_date
        raise InvalidConfiguration("no inspected pinned day is available")


def load_manifest(path: Path) -> PinnedManifest:
    if not path.is_file():
        raise InvalidConfiguration("pinned manifest is missing", details={"path": str(path)})
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise InvalidConfiguration("pinned manifest is not valid JSON") from exc
    files = tuple(
        PinnedFile(
            dispatch_date=date.fromisoformat(item["dispatch_date"]),
            filename=item["filename"],
            url=item.get("url", ""),
            listing_size_bytes=item.get("listing_size_bytes"),
            sha256=item.get("sha256"),
            inspection_status=item.get("inspection_status", "unverified"),
        )
        for item in raw["files"]
    )
    return PinnedManifest(
        schema_version=int(raw["schema_version"]),
        region_id=raw["region_id"],
        start_date=date.fromisoformat(raw["start_date"]),
        end_date=date.fromisoformat(raw["end_date"]),
        default_date=date.fromisoformat(raw["default_date"]),
        source_base_url=raw["source_base_url"],
        files=files,
        retrieved_at_utc=raw.get("retrieved_at_utc"),
        validator_version=raw.get("validator_version"),
    )


def verify_pinned_bytes(manifest: PinnedManifest, pinned_dir: Path) -> list[dict[str, object]]:
    import hashlib

    reports: list[dict[str, object]] = []
    for item in manifest.files:
        path = pinned_dir / item.filename
        present = path.is_file()
        digest = hashlib.sha256(path.read_bytes()).hexdigest() if present else None
        size = path.stat().st_size if present else None
        hash_ok = bool(item.sha256) and digest == item.sha256
        size_ok = item.listing_size_bytes is None or size == item.listing_size_bytes
        status = item.inspection_status
        if item.inspection_status == "passed":
            if not present:
                raise ArchiveNotFound(f"passed pinned file missing: {item.filename}")
            if not hash_ok:
                raise HashMismatch(
                    f"passed pinned file hash mismatch: {item.filename}",
                    details={"expected": item.sha256, "actual": digest},
                )
            if not size_ok:
                raise HashMismatch(f"passed pinned file size mismatch: {item.filename}")
        reports.append(
            {
                "dispatch_date": item.dispatch_date.isoformat(),
                "filename": item.filename,
                "present": present,
                "size_bytes": size,
                "sha256": digest,
                "hash_match": hash_ok,
                "inspection_status": status,
            }
        )
    return reports


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
