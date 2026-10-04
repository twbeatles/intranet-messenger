from pathlib import Path
import re


def test_index_referenced_assets_exist(client):
    response = client.get("/")
    assert response.status_code == 200

    html = response.get_data(as_text=True)
    asset_paths = re.findall(r'(?:src|href)="(/static/[^"]+)"', html)
    assert asset_paths, "no static assets referenced from index"

    project_root = Path(__file__).resolve().parents[1]
    missing = []
    for asset_path in asset_paths:
        relative_path = asset_path.split("?", 1)[0].lstrip("/")
        asset_file = project_root / relative_path
        if not asset_file.exists():
            missing.append(relative_path)

    assert not missing, f"missing static assets: {missing}"


def test_upload_service_exposes_scan_retry_cancel_facade():
    """스캔 재시도/취소 facade와 API 경로가 프론트에 연결되어 있다."""
    project_root = Path(__file__).resolve().parents[1]
    service = (project_root / "static/js/services/upload-service.js").read_text(encoding="utf-8")

    assert "retryUploadScanJob" in service
    assert "cancelUploadScanJob" in service
    assert "/api/upload/jobs/" in service
    assert "MessengerUpload" in service
