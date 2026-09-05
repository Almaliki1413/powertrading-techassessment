"""Allowlisted AEMO DispatchIS archive client. Accepts ISO dates only — never client URLs."""

from __future__ import annotations

import hashlib
import os
import tempfile
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlparse

import httpx

from app.domain.errors import ArchiveNotFound, HashMismatch, InvalidDateRange, UnsafeArchive
from app.settings import Settings

ALLOWED_HOSTS = {"nemweb.com.au", "www.nemweb.com.au"}
ALLOWED_PATH_PREFIX = "/Reports/Archive/DispatchIS_Reports/"
MAX_DOWNLOAD_BYTES = 80 * 1024 * 1024


def archive_filename(day: date) -> str:
    return f"PUBLIC_DISPATCHIS_{day.strftime('%Y%m%d')}.zip"


def archive_url(day: date, base_url: str) -> str:
    base = base_url if base_url.endswith("/") else base_url + "/"
    return f"{base}{archive_filename(day)}"


def validate_range(start: date, end: date, max_days: int) -> tuple[date, ...]:
    if end < start:
        raise InvalidDateRange("end_date must be on or after start_date")
    days = (end - start).days + 1
    if days > max_days:
        raise InvalidDateRange(
            f"range exceeds {max_days}-day interactive cap",
            details={"days": days, "max": max_days},
        )
    return tuple(start + timedelta(days=i) for i in range(days))


def _assert_allowlisted(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise UnsafeArchive("non-HTTPS archive URL rejected", details={"url": url})
    host = (parsed.hostname or "").lower()
    if host not in ALLOWED_HOSTS:
        raise UnsafeArchive("archive host is not allowlisted", details={"host": host})
    path = parsed.path or ""
    if not path.startswith(ALLOWED_PATH_PREFIX):
        raise UnsafeArchive("archive path is not allowlisted", details={"path": path})
    if not path.endswith(".zip") or "PUBLIC_DISPATCHIS_" not in path:
        raise UnsafeArchive("archive filename is not a DispatchIS zip", details={"path": path})


class ArchiveClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.raw_cache = settings.cache_dir / "raw" / "sha256"
        self.raw_cache.mkdir(parents=True, exist_ok=True)

    def load_pinned(self, day: date, expected_sha256: str, expected_size: int | None = None) -> tuple[bytes, str]:
        path = self.settings.pinned_dir / archive_filename(day)
        if not path.is_file():
            raise ArchiveNotFound(
                f"pinned archive missing for {day.isoformat()}",
                details={"filename": path.name},
            )
        data = path.read_bytes()
        if expected_size is not None and len(data) != expected_size:
            raise HashMismatch(
                "pinned listing size mismatch",
                details={"filename": path.name, "expected": expected_size, "actual": len(data)},
            )
        digest = hashlib.sha256(data).hexdigest()
        if digest != expected_sha256.lower():
            raise HashMismatch(
                "pinned SHA-256 mismatch",
                details={"filename": path.name, "expected": expected_sha256, "actual": digest},
            )
        if not data.startswith(b"PK"):
            raise UnsafeArchive("pinned file is not a ZIP", details={"filename": path.name})
        return data, digest

    def download(self, day: date) -> tuple[bytes, str]:
        url = archive_url(day, str(self.settings.aemo_base_url))
        _assert_allowlisted(url)
        timeout = httpx.Timeout(
            connect=self.settings.http_connect_timeout_s,
            read=self.settings.http_read_timeout_s,
            write=self.settings.http_read_timeout_s,
            pool=self.settings.http_connect_timeout_s,
        )
        last_error: Exception | None = None
        for attempt in range(self.settings.http_retries + 1):
            try:
                return self._stream_download(url, timeout)
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                last_error = exc
                if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code in {404, 410}:
                    raise ArchiveNotFound(
                        f"AEMO archive not found for {day.isoformat()}",
                        details={"url": url, "status": exc.response.status_code},
                    ) from exc
                if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code < 500:
                    raise
        raise ArchiveNotFound(
            f"AEMO archive download failed for {day.isoformat()}",
            details={"error": str(last_error)},
        )

    def _stream_download(self, url: str, timeout: httpx.Timeout) -> tuple[bytes, str]:
        hasher = hashlib.sha256()
        collected = bytearray()
        with httpx.Client(timeout=timeout, follow_redirects=False) as client:
            current = url
            for _ in range(5):
                _assert_allowlisted(current)
                response = client.get(current)
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise UnsafeArchive("redirect without Location")
                    current = str(response.url.join(location))
                    continue
                response.raise_for_status()
                for chunk in response.iter_bytes():
                    collected.extend(chunk)
                    hasher.update(chunk)
                    if len(collected) > MAX_DOWNLOAD_BYTES:
                        raise UnsafeArchive("download exceeded byte cap")
                break
            else:
                raise UnsafeArchive("too many redirects")
        data = bytes(collected)
        if not data.startswith(b"PK"):
            raise UnsafeArchive("downloaded bytes are not a ZIP")
        digest = hasher.hexdigest()
        self._atomic_store(digest, data)
        return data, digest

    def _atomic_store(self, digest: str, data: bytes) -> Path:
        dest = self.raw_cache / f"{digest}.zip"
        if dest.exists():
            return dest
        dest.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(prefix=digest, suffix=".tmp", dir=dest.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, dest)
        finally:
            if os.path.exists(tmp_name):
                os.remove(tmp_name)
        return dest
