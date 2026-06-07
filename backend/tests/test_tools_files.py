import io
import uuid
from typing import Any

from agent_capability_support import memory_session
from db.models import ToolDefinition, User
from app.services.tools.builtins.registry import BUILTIN_TOOLS
from app.services.tools.catalog import list_tools


def unwrap(body: dict[str, Any]) -> Any:
    return body.get("data", body)


def test_tool_catalog_dedupes_legacy_duplicate_builtin_display() -> None:
    db = memory_session()
    user = User(email="tool-dedupe@example.com", username="tool-dedupe", password_hash="x")
    db.add(user)
    db.flush()
    builtin = BUILTIN_TOOLS["artifact.create_pdf"]
    db.add(
        ToolDefinition(
            owner_id=user.id,
            name="legacy_create_pdf_duplicate",
            display_name=builtin.display_name,
            description="legacy duplicate",
            category=builtin.category,
            type="custom_python",
            status="active",
        )
    )
    db.commit()

    tools = list_tools(db, user)
    pdf_tools = [
        item
        for item in tools
        if item["display_name"] == builtin.display_name and item["category"] == builtin.category
    ]

    assert [item["name"] for item in pdf_tools] == ["artifact.create_pdf"]


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


def test_txt_and_docx_uploads_enter_message_attachment_context(
    client: Any,
    auth_headers: dict[str, str],
    conversation_id: str,
) -> None:
    text_upload = client.post(
        "/api/v1/files/upload",
        data={"conversation_id": conversation_id},
        files={
            "file": (
                "notes.txt",
                io.BytesIO("Plain text recognition works.".encode("utf-8")),
                "text/plain; charset=utf-8",
            )
        },
        headers=auth_headers,
    )
    assert text_upload.status_code == 200, text_upload.text
    text_asset = unwrap(text_upload.json())
    assert text_asset["parse_status"] == "parsed"
    assert text_asset["metadata"]["extractor"] == "native_text"

    docx_upload = client.post(
        "/api/v1/files/upload",
        data={"conversation_id": conversation_id},
        files={
            "file": (
                "brief.docx",
                io.BytesIO(_docx_bytes("Word recognition works.")),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
        headers=auth_headers,
    )
    assert docx_upload.status_code == 200, docx_upload.text
    docx_asset = unwrap(docx_upload.json())
    assert docx_asset["parse_status"] == "parsed"
    assert docx_asset["metadata"]["extractor"] == "python-docx"

    message = client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={
            "content_type": "text",
            "content": {
                "text": "read these files",
                "attachments": [
                    {"file_id": text_asset["id"]},
                    {"file_id": docx_asset["id"]},
                ],
            },
        },
        headers=auth_headers,
    )
    assert message.status_code == 200, message.text
    attachments = unwrap(message.json())["rawContent"]["attachments"]
    by_name = {item["filename"]: item for item in attachments}
    assert "Plain text recognition works." in by_name["notes.txt"]["extracted_text"]
    assert "Word recognition works." in by_name["brief.docx"]["extracted_text"]


def test_image_upload_infers_workspace_and_exposes_ocr_text(
    client: Any,
    auth_headers: dict[str, str],
    monkeypatch: Any,
) -> None:
    from app.services.tools.builtins.file import converters as file_converters

    monkeypatch.setattr(
        file_converters,
        "_text_from_image_rapidocr",
        lambda path: (
            "HELLO OCR",
            {
                "extractor": "image_ocr",
                "vision_status": "parsed",
                "ocr_available": True,
                "ocr_engine": "rapidocr",
            },
        ),
    )
    monkeypatch.setattr(
        file_converters,
        "_text_from_image_tesseract",
        lambda path: (
            "",
            {
                "extractor": "image_ocr",
                "vision_status": "missing_tesseract",
                "ocr_available": False,
                "ocr_engine": "tesseract",
            },
        ),
    )

    workspace = client.post(
        "/api/v1/workspaces",
        json={
            "name": f"OCR Workspace {uuid.uuid4().hex[:8]}",
            "description": "ocr",
            "type": "custom",
        },
        headers=auth_headers,
    )
    assert workspace.status_code == 200, workspace.text
    workspace_id = unwrap(workspace.json())["id"]

    conversation = client.post(
        "/api/v1/conversations",
        json={
            "title": "Image OCR",
            "chat_type": "single",
            "workspace_id": workspace_id,
        },
        headers=auth_headers,
    )
    assert conversation.status_code == 200, conversation.text
    conversation_id = unwrap(conversation.json())["id"]

    uploaded = client.post(
        "/api/v1/files/upload",
        data={"conversation_id": conversation_id},
        files={
            "file": (
                "Figure_1.png",
                io.BytesIO(b"\x89PNG\r\n\x1a\nfake"),
                "image/png",
            )
        },
        headers=auth_headers,
    )
    assert uploaded.status_code == 200, uploaded.text
    file_asset = unwrap(uploaded.json())
    file_id = file_asset["id"]

    assert file_asset["workspace_id"] == workspace_id
    assert file_asset["parse_status"] == "parsed"
    assert file_asset["metadata"]["workspace_id"] == workspace_id
    assert file_asset["metadata"]["ocr_engine"] == "rapidocr"

    tree_response = client.get(
        f"/api/v1/workspaces/{workspace_id}/files/tree",
        headers=auth_headers,
    )
    assert tree_response.status_code == 200, tree_response.text
    flat_nodes = _flatten_tree(unwrap(tree_response.json())["root"])
    uploaded_node = next(item for item in flat_nodes if item.get("id") == f"file:{file_id}")
    assert uploaded_node["source"] == "upload"
    assert uploaded_node["path"].startswith(f"uploads/conversations/{conversation_id}/")

    message = client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={
            "content_type": "text",
            "content": {
                "text": "recognize this image",
                "attachments": [{"file_id": file_id}],
            },
        },
        headers=auth_headers,
    )
    assert message.status_code == 200, message.text
    attachment = unwrap(message.json())["rawContent"]["attachments"][0]
    assert attachment["extracted_text"] == "HELLO OCR"
    assert attachment["metadata"]["vision_status"] == "parsed"


def _flatten_tree(node: dict[str, Any]) -> list[dict[str, Any]]:
    items = [node]
    for child in node.get("children") or []:
        items.extend(_flatten_tree(child))
    return items


def _docx_bytes(text: str) -> bytes:
    from docx import Document

    buffer = io.BytesIO()
    document = Document()
    document.add_paragraph(text)
    document.save(buffer)
    return buffer.getvalue()
