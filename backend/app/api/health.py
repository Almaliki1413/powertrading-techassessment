from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter

from app import BENCHMARK_LABEL
from app.application.manifest import load_manifest, utc_now, verify_pinned_bytes
from app.infrastructure.optimization.pulp_cbc import query_cbc_identity
from app.settings import Settings, get_settings

router = APIRouter()
ROOT = Path(__file__).resolve().parents[3]


def _build_info() -> dict[str, object]:
    path = ROOT / "build-info.json"
    if path.is_file():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"status": "unrecorded"}


@router.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "benchmark_label": BENCHMARK_LABEL,
        "build": _build_info(),
    }


@router.get("/ready")
def ready() -> dict[str, object]:
    settings: Settings = get_settings()
    settings.cache_dir.mkdir(parents=True, exist_ok=True)
    probe = settings.cache_dir / ".write_probe"
    probe.write_text("ok", encoding="utf-8")
    probe.unlink(missing_ok=True)
    manifest = load_manifest(settings.manifest_path)
    files = verify_pinned_bytes(manifest, settings.pinned_dir)
    identity = query_cbc_identity()
    binary_ok = bool(identity.executable_path)
    if not binary_ok and identity.cbc_version == "unknown":
        from app.domain.errors import SolverUnavailable

        raise SolverUnavailable("CBC executable is not queryable")
    passed = [f for f in files if f["inspection_status"] == "passed"]
    if not passed:
        from app.domain.errors import ArchiveNotFound

        raise ArchiveNotFound("no inspected pinned archive")
    return {
        "status": "ready",
        "checked_at": utc_now(),
        "manifest": {
            "start_date": manifest.start_date.isoformat(),
            "end_date": manifest.end_date.isoformat(),
            "default_date": manifest.approved_default().isoformat(),
        },
        "pinned_files": files,
        "cbc": {
            "version": identity.cbc_version,
            "path": identity.executable_path,
            "sha256": identity.executable_sha256,
            "pulp_version": identity.pulp_version,
        },
        "cache_writable": True,
    }
