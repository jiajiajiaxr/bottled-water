import sys
from pathlib import Path
from typing import Any


def test_artifact_classifier_only_for_deliverable_requests() -> None:
    backend_dir = Path(__file__).resolve().parents[1] / "backend"
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))

    from app.services.artifacts import classify_artifact_request

    assert classify_artifact_request("你好，今天能聊聊吗？") is None
    assert classify_artifact_request("帮我生成一个答辩用 Word 文档") == "document"
    assert classify_artifact_request("做一个数据看板网页并支持预览") == "web_app"


def test_artifact_preview_contract(
    client: Any,
    api_paths: dict[str, str],
    auth_headers: dict[str, str],
    conversation_id: str,
) -> None:
    response = client.post(
        api_paths["artifacts"],
        json={
            "conversation_id": conversation_id,
            "kind": "preview",
            "title": "Acceptance Preview",
            "content": {"html": "<main>Acceptance Preview</main>"},
        },
        headers=auth_headers,
    )

    assert response.status_code in {200, 201, 202}, response.text
    body = response.json()
    assert body.get("id") or body.get("artifact_id")
    assert body.get("kind") in {None, "preview", "app", "html"}

    artifact_id = body.get("id") or body.get("artifact_id")
    exports = client.get(f"/api/v1/artifacts/{artifact_id}/exports", headers=auth_headers)
    assert exports.status_code == 200, exports.text
    export_body = exports.json()["data"]
    assert export_body["formats"] == [
        {
            "format": export_body["default_format"],
            "url": f"/api/v1/artifacts/{artifact_id}/export?format={export_body['default_format']}",
        }
    ]

    exported = client.get(f"/api/v1/artifacts/{artifact_id}/export?format=zip", headers=auth_headers)
    assert exported.status_code == 200, exported.text
    assert exported.headers["content-type"].startswith("application/zip")
    assert "filename*=" in exported.headers["content-disposition"]

    exported_json = client.get(f"/api/v1/artifacts/{artifact_id}/export?format=json", headers=auth_headers)
    assert exported_json.status_code == 200, exported_json.text
    assert exported_json.json()["id"] == artifact_id
