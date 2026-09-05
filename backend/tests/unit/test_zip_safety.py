from __future__ import annotations

import io
import zipfile

import pytest

from app.domain.errors import UnsafeArchive
from app.infrastructure.aemo.zip_safety import iter_safe_members


def _zip_bytes(names: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name, data in names.items():
            zf.writestr(name, data)
    return buffer.getvalue()


def test_rejects_path_traversal() -> None:
    data = _zip_bytes({"../secret.csv": b"x"})
    with pytest.raises(UnsafeArchive):
        list(iter_safe_members(data, archive_label="t", allowed_suffixes=(".csv",), max_members=10, max_file_bytes=1000, aggregate_budget=[0]))


def test_rejects_duplicate_names() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("a.csv", b"1")
        info = zipfile.ZipInfo("A.csv")
        zf.writestr(info, b"2")
    # Duplicate via mixed separators that normalize to the same path.
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr("dir/file.csv", b"1")
        zf.writestr("dir\\file.csv", b"2")
    with pytest.raises(UnsafeArchive):
        list(
            iter_safe_members(
                buffer.getvalue(),
                archive_label="t",
                allowed_suffixes=(".csv",),
                max_members=10,
                max_file_bytes=1000,
                aggregate_budget=[0],
            )
        )


def test_rejects_unexpected_type() -> None:
    data = _zip_bytes({"notes.txt": b"hello"})
    with pytest.raises(UnsafeArchive):
        list(
            iter_safe_members(
                data,
                archive_label="t",
                allowed_suffixes=(".zip",),
                max_members=10,
                max_file_bytes=1000,
                aggregate_budget=[0],
            )
        )


def test_rejects_missing_signature() -> None:
    with pytest.raises(UnsafeArchive):
        list(
            iter_safe_members(
                b"not-a-zip",
                archive_label="t",
                allowed_suffixes=(".zip",),
                max_members=10,
                max_file_bytes=1000,
                aggregate_budget=[0],
            )
        )
