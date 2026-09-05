from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app

PINNED = Path(__file__).resolve().parents[3] / "data" / "pinned" / "PUBLIC_DISPATCHIS_20260826.zip"


@pytest.mark.skipif(not PINNED.is_file(), reason="inspected archive not present")
def test_resolve_and_optimize_inspected_day() -> None:
    client = TestClient(create_app())
    resolved = client.post(
        "/api/v1/datasets/resolve",
        json={"start_date": "2026-08-26", "end_date": "2026-08-26", "source_mode": "pinned"},
    )
    assert resolved.status_code == 200
    body = resolved.json()
    assert body["days"][0]["selectable"] is True
    result = client.post(
        "/api/v1/optimizations",
        json={
            "dataset_id": body["dataset_id"],
            "selected_date": "2026-08-26",
            "mode": "independent_day",
        },
    )
    assert result.status_code == 200, result.text
    payload = result.json()
    assert payload["benchmark_label"].startswith("Perfect-hindsight")
    assert payload["metrics"]["verification_passed"] is True
    assert len(payload["decisions"]) == 288
    assert payload["decisions"][0]["interval_end"].startswith("2026-08-26T00:05")
    assert payload["decisions"][-1]["interval_end"].startswith("2026-08-27T00:00")
