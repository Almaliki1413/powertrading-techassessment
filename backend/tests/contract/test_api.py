from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Settings


def test_health_does_not_depend_on_data() -> None:
    app = create_app(Settings())
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers.get("x-request-id")


def test_invalid_resolve_range_problem_details(tmp_path) -> None:
    manifest = {
        "schema_version": 1,
        "region_id": "NSW1",
        "start_date": "2026-08-26",
        "end_date": "2026-09-01",
        "default_date": "2026-09-01",
        "source_base_url": "https://nemweb.com.au/Reports/Archive/DispatchIS_Reports/",
        "files": [
            {
                "dispatch_date": "2026-08-26",
                "filename": "PUBLIC_DISPATCHIS_20260826.zip",
                "url": "https://nemweb.com.au/Reports/Archive/DispatchIS_Reports/PUBLIC_DISPATCHIS_20260826.zip",
                "listing_size_bytes": 1,
                "sha256": "aa",
                "inspection_status": "unverified",
            }
        ],
        "retrieved_at_utc": None,
        "validator_version": "1.0.0",
    }
    import json

    pinned = tmp_path / "pinned"
    pinned.mkdir()
    (pinned / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    settings = Settings(data_dir=tmp_path)
    client = TestClient(create_app(settings))
    response = client.post(
        "/api/v1/datasets/resolve",
        json={"start_date": "2026-09-02", "end_date": "2026-08-01", "source_mode": "pinned"},
    )
    assert response.status_code in {400, 422}
    body = response.json()
    assert body["code"] in {"INVALID_DATE_RANGE", "INVALID_CONFIGURATION"}
    assert body["blocking"] is True
    assert body["request_id"]
