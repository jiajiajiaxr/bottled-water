import io
import uuid
from typing import Any


def unwrap(body: dict[str, Any]) -> Any:
    return body.get("data", body)


def test_tool_catalog_create_invoke_and_artifact_tool(
    client: Any,
    auth_headers: dict[str, str],
    conversation_id: str,
) -> None:
    listed = client.get("/api/v1/tools", headers=auth_headers)
    assert listed.status_code == 200, listed.text
    tools = unwrap(listed.json())["items"]
    names = [item["name"] for item in tools]
    assert len(names) == len(set(names))
    assert "file.extract_text" in names
    assert "file.preview" in names
    assert "file.summarize" in names
    assert "artifact.create_pdf" in names
    assert "sandbox.run" in names

    tool_name = f"custom_echo_acceptance_{uuid.uuid4().hex[:8]}"
    created = client.post(
        "/api/v1/tools",
        json={
            "name": tool_name,
            "display_name": "Echo Acceptance",
            "description": "Echoes a value from arguments.",
            "category": "qa",
            "implementation": {
                "language": "python",
                "code": "text = str(arguments.get('input') or '')\nresult = {'echo': text, 'length': len(text)}",
            },
            "permissions": ["tool:invoke"],
        },
        headers=auth_headers,
    )
    assert created.status_code == 200, created.text
    tool = unwrap(created.json())
    assert tool["implementation"]["source_path"].endswith(".py")

    invoked = client.post(
        f"/api/v1/tools/{tool['id']}/invoke",
        json={"arguments": {"input": "hello"}},
        headers=auth_headers,
    )
    assert invoked.status_code == 200, invoked.text
    assert unwrap(invoked.json())["result"]["result"]["echo"] == "hello"

    artifact = client.post(
        "/api/v1/tools/artifact.create_pdf/invoke",
        json={
            "arguments": {
                "conversation_id": conversation_id,
                "title": "PDF Acceptance Plan",
                "body": "目标\n范围\n验收标准",
            }
        },
        headers=auth_headers,
    )
    assert artifact.status_code == 200, artifact.text
    result = unwrap(artifact.json())["result"]
    assert result["format"] == "pdf"
    exported = client.get(result["export_url"], headers=auth_headers)
    assert exported.status_code == 200, exported.text
    assert exported.headers["content-type"].startswith("application/pdf")


def test_file_tool_chain_extract_preview_summarize_embed_convert(
    client: Any,
    auth_headers: dict[str, str],
    conversation_id: str,
) -> None:
    uploaded = client.post(
        "/api/v1/files/upload",
        data={"conversation_id": conversation_id},
        files={"file": ("notes.md", io.BytesIO("## 标题\n这是一个 AgentHub 文件工具测试。".encode("utf-8")), "text/markdown")},
        headers=auth_headers,
    )
    assert uploaded.status_code == 200, uploaded.text
    file_id = unwrap(uploaded.json())["id"]

    extracted = client.post(
        "/api/v1/tools/file.extract_text/invoke",
        json={"arguments": {"file_id": file_id}},
        headers=auth_headers,
    )
    assert extracted.status_code == 200, extracted.text
    assert "AgentHub" in unwrap(extracted.json())["result"]["text"]

    preview = client.get(f"/api/v1/files/{file_id}/preview", headers=auth_headers)
    assert preview.status_code == 200, preview.text
    assert unwrap(preview.json())["mode"] == "text"

    summary = client.post(f"/api/v1/files/{file_id}/summarize", headers=auth_headers)
    assert summary.status_code == 200, summary.text
    assert "AgentHub" in unwrap(summary.json())["summary"]

    embedding = client.post(f"/api/v1/files/{file_id}/embed", headers=auth_headers)
    assert embedding.status_code == 200, embedding.text
    assert unwrap(embedding.json())["dimensions"] == 32

    converted = client.get(f"/api/v1/files/{file_id}/convert?format=docx", headers=auth_headers)
    assert converted.status_code == 200, converted.text
    assert converted.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
