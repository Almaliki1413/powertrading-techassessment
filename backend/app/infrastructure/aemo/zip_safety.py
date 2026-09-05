"""ZIP safety: no extractall, bounded members, no traversal/symlink/encryption."""

from __future__ import annotations

import io
import posixpath
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass

from app.domain.errors import UnsafeArchive

MAX_OUTER_MEMBERS_PER_DAY = 1000
MAX_NESTING_DEPTH = 2
MAX_CSV_BYTES = 64 * 1024 * 1024
MAX_AGGREGATE_DECOMPRESSED_BYTES = 512 * 1024 * 1024
MAX_COMPRESSION_RATIO = 100.0
ZIP_MAGIC = b"PK"


@dataclass(frozen=True, slots=True)
class SafeMember:
    name: str
    file_size: int
    compress_size: int
    data: bytes


def _normalize(name: str) -> str:
    replaced = name.replace("\\", "/")
    return posixpath.normpath(replaced)


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    unix_mode = (info.external_attr >> 16) & 0o170000
    return unix_mode == 0o120000 or info.create_system == 3 and bool(info.external_attr & 0xA0000000)


def validate_member_name(name: str, *, archive_label: str) -> str:
    if "\x00" in name:
        raise UnsafeArchive("NUL in ZIP member name", details={"archive": archive_label, "name": name})
    if name.startswith("/") or name.startswith("\\") or (len(name) >= 2 and name[1] == ":"):
        raise UnsafeArchive(
            "absolute or drive-prefixed ZIP member rejected",
            details={"archive": archive_label, "name": name},
        )
    normalized = _normalize(name)
    if normalized.startswith("..") or "/../" in f"/{normalized}/" or normalized == "..":
        raise UnsafeArchive("path traversal in ZIP member", details={"archive": archive_label, "name": name})
    if normalized.startswith("/") or normalized == ".":
        raise UnsafeArchive("unsafe normalized ZIP member", details={"archive": archive_label, "name": name})
    return normalized


def _check_info(info: zipfile.ZipInfo, *, archive_label: str) -> str:
    name = validate_member_name(info.filename, archive_label=archive_label)
    if info.flag_bits & 0x1:
        raise UnsafeArchive("encrypted ZIP member rejected", details={"archive": archive_label, "name": name})
    if _is_symlink(info):
        raise UnsafeArchive("symlink ZIP member rejected", details={"archive": archive_label, "name": name})
    if info.file_size < 0 or info.compress_size < 0:
        raise UnsafeArchive("negative ZIP sizes", details={"archive": archive_label, "name": name})
    if info.compress_size > 0:
        ratio = info.file_size / max(info.compress_size, 1)
        if ratio > MAX_COMPRESSION_RATIO:
            raise UnsafeArchive(
                "compression ratio exceeds 100:1",
                details={"archive": archive_label, "name": name, "ratio": ratio},
            )
    return name


def require_zip_signature(data: bytes, *, archive_label: str) -> None:
    if not data.startswith(ZIP_MAGIC):
        raise UnsafeArchive("missing ZIP signature", details={"archive": archive_label})


def iter_safe_members(
    data: bytes,
    *,
    archive_label: str,
    allowed_suffixes: tuple[str, ...],
    max_members: int,
    max_file_bytes: int,
    aggregate_budget: list[int],
) -> Iterator[SafeMember]:
    require_zip_signature(data, archive_label=archive_label)
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise UnsafeArchive("invalid ZIP", details={"archive": archive_label, "error": str(exc)}) from exc

    names: set[str] = set()
    with zf:
        infos = zf.infolist()
        if len(infos) > max_members:
            raise UnsafeArchive(
                f"more than {max_members} members",
                details={"archive": archive_label, "count": len(infos)},
            )
        for info in infos:
            if info.is_dir():
                continue
            name = _check_info(info, archive_label=archive_label)
            if name in names:
                raise UnsafeArchive(
                    "duplicate normalized ZIP member name",
                    details={"archive": archive_label, "name": name},
                )
            names.add(name)
            lower = name.lower()
            if not any(lower.endswith(suffix) for suffix in allowed_suffixes):
                raise UnsafeArchive(
                    "unexpected ZIP member type",
                    details={"archive": archive_label, "name": name},
                )
            if info.file_size > max_file_bytes:
                raise UnsafeArchive(
                    "decompressed member exceeds size cap",
                    details={"archive": archive_label, "name": name, "file_size": info.file_size},
                )
            if aggregate_budget[0] + info.file_size > MAX_AGGREGATE_DECOMPRESSED_BYTES:
                raise UnsafeArchive(
                    "aggregate decompressed size exceeds 512 MiB/day",
                    details={"archive": archive_label, "name": name},
                )
            try:
                raw = zf.read(info)
            except Exception as exc:  # CRC / integrity
                raise UnsafeArchive(
                    "ZIP CRC or integrity failure",
                    details={"archive": archive_label, "name": name, "error": str(exc)},
                ) from exc
            if len(raw) != info.file_size:
                raise UnsafeArchive(
                    "decompressed size mismatch",
                    details={"archive": archive_label, "name": name},
                )
            aggregate_budget[0] += len(raw)
            yield SafeMember(
                name=name,
                file_size=info.file_size,
                compress_size=info.compress_size,
                data=raw,
            )
