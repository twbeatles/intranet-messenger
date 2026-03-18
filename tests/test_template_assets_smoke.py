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
