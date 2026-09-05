from __future__ import annotations

from fastapi import APIRouter, Request

from app import BENCHMARK_LABEL, PARSER_VERSION, REGION_ID, VALIDATOR_VERSION
from app.api.problem_details import request_id_for
from app.application.manifest import load_manifest
from app.domain.models import BatteryConfig
from app.settings import get_settings

router = APIRouter()


@router.get("/config")
def get_config(request: Request) -> dict[str, object]:
    settings = get_settings()
    manifest = load_manifest(settings.manifest_path)
    battery = BatteryConfig()
    return {
        "request_id": request_id_for(request),
        "benchmark_label": BENCHMARK_LABEL,
        "region_id": REGION_ID,
        "parser_version": PARSER_VERSION,
        "validator_version": VALIDATOR_VERSION,
        "source_mode_default": settings.source_mode,
        "pinned_range": {
            "start_date": manifest.start_date.isoformat(),
            "end_date": manifest.end_date.isoformat(),
            "default_date": manifest.approved_default().isoformat(),
            "manifest_default_date": manifest.default_date.isoformat(),
        },
        "battery": battery.canonical_dict(),
        "limits": {
            "max_range_days": settings.max_range_days,
            "solver_timeout_s": settings.solver_timeout_s,
            "max_concurrent_solves": settings.max_concurrent_solves,
            "queue_timeout_s": settings.queue_timeout_s,
        },
        "aemo_base_url": str(settings.aemo_base_url),
    }
