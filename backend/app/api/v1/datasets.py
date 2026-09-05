from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.api.problem_details import request_id_for
from app.application.manifest import load_manifest, verify_pinned_bytes
from app.application.resolve_dataset import ResolveDataset, quality_to_dict
from app.settings import get_settings

router = APIRouter()


class ResolveRequest(BaseModel):
    start_date: date
    end_date: date
    source_mode: str = Field(default="pinned")


def _resolver(request: Request) -> ResolveDataset:
    return request.app.state.resolver


@router.get("/datasets/pinned")
def pinned_dataset(request: Request) -> dict[str, object]:
    settings = get_settings()
    manifest = load_manifest(settings.manifest_path)
    files = verify_pinned_bytes(manifest, settings.pinned_dir)
    return {
        "request_id": request_id_for(request),
        "schema_version": manifest.schema_version,
        "region_id": manifest.region_id,
        "start_date": manifest.start_date.isoformat(),
        "end_date": manifest.end_date.isoformat(),
        "default_date": manifest.approved_default().isoformat(),
        "manifest_default_date": manifest.default_date.isoformat(),
        "source_base_url": manifest.source_base_url,
        "retrieved_at_utc": manifest.retrieved_at_utc,
        "validator_version": manifest.validator_version,
        "files": files,
    }


@router.post("/datasets/resolve")
def resolve_dataset(body: ResolveRequest, request: Request) -> dict[str, object]:
    reference = _resolver(request).execute(body.start_date, body.end_date, body.source_mode)
    return {
        "request_id": request_id_for(request),
        "dataset_id": reference.dataset_id,
        "start_date": reference.start_date.isoformat(),
        "end_date": reference.end_date.isoformat(),
        "source_mode": reference.source_mode,
        "region_id": reference.region_id,
        "days": [
            {
                "date": day.date.isoformat(),
                "status": day.status,
                "selectable": day.selectable,
                "interval_count": day.interval_count,
                "rrp_min": day.rrp_min,
                "rrp_max": day.rrp_max,
                "blocking_code": day.blocking_code,
                "blocking_message": day.blocking_message,
                "source_hash": day.source_hash,
                "inspection_status": day.inspection_status,
            }
            for day in reference.days
        ],
    }


@router.get("/datasets/{dataset_id}/days")
def list_days(dataset_id: str, request: Request) -> dict[str, object]:
    reference = _resolver(request).get(dataset_id)
    days = []
    for summary in reference.days:
        payload: dict[str, object] = {
            "date": summary.date.isoformat(),
            "status": summary.status,
            "selectable": summary.selectable,
            "interval_count": summary.interval_count,
            "rrp_min": summary.rrp_min,
            "rrp_max": summary.rrp_max,
            "blocking_code": summary.blocking_code,
            "blocking_message": summary.blocking_message,
        }
        validated = reference.validated.get(summary.date)
        if validated is not None:
            payload["dataset_hash"] = validated.dataset_hash
            payload["quality"] = quality_to_dict(validated.quality_report)
        days.append(payload)
    return {"request_id": request_id_for(request), "dataset_id": dataset_id, "days": days}
