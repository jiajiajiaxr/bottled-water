from __future__ import annotations

import asyncio
import shutil
import subprocess
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from db.base import Base
from app.core.errors import ValidationAppError
from db.models import Artifact, Conversation, FileAsset, Message, SandboxSession, ToolInvocation, User, Workspace, WorkspaceMember
from app.api.artifacts import download_artifact_preview_pdf
from app.api.messages import _send
from app.api.workspace_files import download_workspace_file, download_workspace_file_preview_pdf, preview_workspace_file
from app.services.chat.code_runner import run_message_code_block
from app.services.files.workspace_tree import (
    bulk_delete_workspace_file_nodes,
    create_workspace_folder,
    delete_workspace_file_node,
    move_workspace_file_nodes,
    rename_workspace_file_node,
    set_workspace_file_favorite,
    workspace_file_tree,
)
from app.services.files.previewers import office as office_preview
from app.services.tools.builtins.file.preview import preview_payload
from app.services.tools.executor import invoke_tool
from app.services.workspaces.filesystem import scoped_dir, workspace_root


@pytest.fixture
def db() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def test_workspace_directories_are_isolated(db: Session) -> None:
    user = _user()
    left = _workspace(user, "left")
    right = _workspace(user, "right")
    db.add_all([user, left, right])
    db.commit()

    try:
        left_root = workspace_root(left.id)
        right_root = workspace_root(right.id)

        assert left_root != right_root
        assert {item.name for item in left_root.iterdir()} >= {"files", "artifacts", "sandbox", "tools", "logs"}
        assert {item.name for item in right_root.iterdir()} >= {"files", "artifacts", "sandbox", "tools", "logs"}
    finally:
        _cleanup(left.id, right.id)


def test_file_write_then_sandbox_run_reads_same_workspace_scope(db: Session) -> None:
    user, workspace, conversation = _user_workspace_conversation(db)
    args = {
        "workspace_id": workspace.id,
        "conversation_id": conversation.id,
        "agent_id": "agent-a",
        "path": "hello.py",
        "content": "print('中文输出')",
    }

    try:
        written = invoke_tool(db, user, "file.write", args)
        result = invoke_tool(
            db,
            user,
            "sandbox.run",
            {
                "workspace_id": workspace.id,
                "conversation_id": conversation.id,
                "agent_id": "agent-a",
                "command": written["result"]["sandbox_command"],
                "timeout": 5,
            },
        )
        session = db.scalar(select(SandboxSession).where(SandboxSession.workspace_id == workspace.id))

        assert written["result"]["status"] == "succeeded"
        assert written["result"]["path"] == "hello.py"
        assert written["result"]["relative_path"] == "hello.py"
        assert written["result"]["sandbox_path"] == "hello.py"
        assert ":" not in written["result"]["path"]
        assert result["result"]["status"] == "succeeded"
        assert "中文输出" in result["result"]["stdout"]
        assert session is not None
        assert session.command_history[0]["cwd"] == result["result"]["cwd"]
        assert any(item["path"] == "hello.py" for item in session.mounted_files)
    finally:
        _cleanup(workspace.id)


def test_sandbox_scopes_do_not_leak_between_workspaces(db: Session) -> None:
    user = _user()
    workspace_a = _workspace(user, "a")
    workspace_b = _workspace(user, "b")
    conversation = Conversation(
        creator_id=user.id,
        chat_type="single",
        title="Isolation",
        extra={"workspace_id": workspace_a.id},
    )
    db.add_all([user, workspace_a, workspace_b, conversation])
    db.commit()

    try:
        invoke_tool(
            db,
            user,
            "file.write",
            {
                "workspace_id": workspace_a.id,
                "conversation_id": conversation.id,
                "path": "secret.txt",
                "content": "workspace-a-only",
            },
        )
        result = invoke_tool(
            db,
            user,
            "sandbox.run",
            {
                "workspace_id": workspace_b.id,
                "conversation_id": conversation.id,
                "command": "python -c \"print(open('secret.txt', encoding='utf-8').read())\"",
                "timeout": 5,
            },
        )

        assert result["result"]["status"] == "failed"
        assert "workspace-a-only" not in result["result"]["stdout"]
    finally:
        _cleanup(workspace_a.id, workspace_b.id)


def test_workspace_file_tree_aggregates_upload_artifact_and_sandbox_files(db: Session) -> None:
    user, workspace, conversation = _user_workspace_conversation(db)
    upload_path = scoped_dir(workspace.id, "uploads", conversation_id=conversation.id) / "notes.md"
    upload_path.write_text("# AgentHub\nworkspace file", encoding="utf-8")
    upload = FileAsset(
        owner_id=user.id,
        conversation_id=conversation.id,
        filename="notes.md",
        original_filename="notes.md",
        content_type="text/markdown",
        size=upload_path.stat().st_size,
        checksum="upload-checksum",
        storage_path=str(upload_path),
        purpose="attachment",
        parse_status="parsed",
        extra={"workspace_id": workspace.id},
    )
    db.add(upload)
    db.commit()

    try:
        invoke_tool(
            db,
            user,
            "artifact.create_html",
            {
                "workspace_id": workspace.id,
                "conversation_id": conversation.id,
                "title": "Demo Page",
                "html": "<h1>Demo</h1>",
            },
        )
        invoke_tool(
            db,
            user,
            "file.write",
            {
                "workspace_id": workspace.id,
                "conversation_id": conversation.id,
                "path": "script.py",
                "content": "print('ok')",
            },
        )

        tree = workspace_file_tree(db, user, workspace.id)
        flat = _flatten(tree["root"])
        paths = {item["path"] for item in flat}
        sources = {item["source"] for item in flat if item["type"] == "file"}

        assert any(path.endswith("notes.md") and path.startswith("uploads/") for path in paths)
        assert any(path.startswith("artifacts/") for path in paths)
        assert any(path.endswith("script.py") and path.startswith("sandbox/") for path in paths)
        assert {"upload", "artifact", "sandbox"} <= sources
    finally:
        _cleanup(workspace.id)


def test_workspace_file_tree_normalizes_display_names_and_conversation_folders(db: Session) -> None:
    user, workspace, conversation = _user_workspace_conversation(db)
    first = scoped_dir(workspace.id, "uploads", conversation_id=conversation.id) / "Figure_1.png"
    second = scoped_dir(workspace.id, "uploads", conversation_id=conversation.id) / "nested" / "Figure_1.png"
    second.parent.mkdir(parents=True, exist_ok=True)
    first.write_bytes(b"fake-image-a")
    second.write_bytes(b"fake-image-b")
    db.add_all(
        [
            FileAsset(
                owner_id=user.id,
                conversation_id=conversation.id,
                filename="Figure_1.png",
                original_filename="Figure_1.png",
                content_type="image/png",
                size=first.stat().st_size,
                checksum="figure-a",
                storage_path=str(first),
                purpose="attachment",
                parse_status="parsed",
                extra={"workspace_id": workspace.id},
            ),
            FileAsset(
                owner_id=user.id,
                conversation_id=conversation.id,
                filename="Figure_1.png",
                original_filename="Figure_1.png",
                content_type="image/png",
                size=second.stat().st_size,
                checksum="figure-b",
                storage_path=str(second),
                purpose="attachment",
                parse_status="parsed",
                extra={"workspace_id": workspace.id},
            ),
        ]
    )
    db.commit()

    try:
        tree = workspace_file_tree(db, user, workspace.id)
        flat = _flatten(tree["root"])
        names = {item.get("display_name") for item in flat}

        assert "上传文件" in names
        assert any(str(name).startswith("单聊：Workspace Sandbox · ") for name in names)
        assert all(item.get("display_name") for item in flat)
    finally:
        _cleanup(workspace.id)


def test_workspace_file_tree_replaces_uuid_directories_with_readable_labels(db: Session) -> None:
    user, workspace, conversation = _user_workspace_conversation(db)
    uuid_dir = "3ef804b7-9a42-4f52-af0e-201238c23bc4"
    path = scoped_dir(workspace.id, "uploads") / "legacy" / uuid_dir / "Figure_1.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"fake-image")

    try:
        tree = workspace_file_tree(db, user, workspace.id)
        flat = _flatten(tree["root"])
        display_names = {str(item.get("display_name") or "") for item in flat}

        assert uuid_dir not in display_names
        assert "上传记录 3ef804b7" in display_names
    finally:
        _cleanup(workspace.id)


def test_workspace_file_tree_labels_conversation_uuid_folders(db: Session) -> None:
    user, workspace, conversation = _user_workspace_conversation(db)
    path = scoped_dir(workspace.id, "uploads") / "legacy" / conversation.id / "Figure_1.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"fake-image")

    try:
        tree = workspace_file_tree(db, user, workspace.id)
        display_names = {str(item.get("display_name") or "") for item in _flatten(tree["root"])}

        assert conversation.id not in display_names
        assert any(
            name.startswith(f"单聊：{conversation.title} · ")
            and name.rsplit(" · ", 1)[-1].isdigit()
            and len(name.rsplit(" · ", 1)[-1]) == 12
            for name in display_names
        )
    finally:
        _cleanup(workspace.id)


def test_workspace_file_preview_supports_pdf_artifact(db: Session) -> None:
    user, workspace, conversation = _user_workspace_conversation(db)

    try:
        result = invoke_tool(
            db,
            user,
            "artifact.create_pdf",
            {
                "workspace_id": workspace.id,
                "conversation_id": conversation.id,
                "title": "PDF 工作区预览",
                "body": "这是用于工作区文件系统预览的 PDF 产物。",
            },
        )["result"]
        node_id = f"artifact:{result['artifact_id']}"

        preview = asyncio.run(preview_workspace_file(workspace.id, node_id, db, user))["data"]
        downloaded = asyncio.run(download_workspace_file(workspace.id, node_id, db, user))

        assert preview["mode"] == "pdf"
        assert preview["artifact_id"] == result["artifact_id"]
        assert preview["content_type"].startswith("application/pdf")
        assert preview["download_url"]
        assert downloaded.media_type == "application/pdf"
        assert downloaded.body.startswith(b"%PDF")
    finally:
        _cleanup(workspace.id)


def test_workspace_file_preview_converts_docx_artifact_to_cached_pdf(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    user, workspace, conversation = _user_workspace_conversation(db)
    calls = _fake_libreoffice(monkeypatch)

    try:
        result = invoke_tool(
            db,
            user,
            "artifact.create_docx",
            {
                "workspace_id": workspace.id,
                "conversation_id": conversation.id,
                "title": "Word 工作区预览",
                "body": "这是用于工作区文件系统预览的 Word 产物。",
            },
        )["result"]
        node_id = f"artifact:{result['artifact_id']}"

        preview = asyncio.run(preview_workspace_file(workspace.id, node_id, db, user))["data"]
        preview_again = asyncio.run(preview_workspace_file(workspace.id, node_id, db, user))["data"]
        pdf = asyncio.run(download_workspace_file_preview_pdf(workspace.id, node_id, db, user))

        assert preview["mode"] == "pdf"
        assert preview["artifact_id"] == result["artifact_id"]
        assert preview["artifact_type"] == "document"
        assert preview["preview_pdf_url"]
        assert preview_again["office_preview"]["cached"] is True
        assert pdf.media_type == "application/pdf"
        assert pdf.path.endswith("preview.pdf")
        assert len(calls) == 1
    finally:
        _cleanup(workspace.id)


def test_chat_artifact_preview_converts_docx_to_pdf(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    user, workspace, conversation = _user_workspace_conversation(db)
    calls = _fake_libreoffice(monkeypatch)

    try:
        result = invoke_tool(
            db,
            user,
            "artifact.create_docx",
            {
                "workspace_id": workspace.id,
                "conversation_id": conversation.id,
                "title": "主聊天 Word 预览",
                "body": "这是用于主聊天产物预览的 Word 文件。",
            },
        )["result"]

        pdf = asyncio.run(download_artifact_preview_pdf(result["artifact_id"], db, user))
        pdf_again = asyncio.run(download_artifact_preview_pdf(result["artifact_id"], db, user))

        assert pdf.media_type == "application/pdf"
        assert pdf.path.endswith("preview.pdf")
        assert pdf_again.path == pdf.path
        assert len(calls) == 1
    finally:
        _cleanup(workspace.id)


def test_workspace_file_preview_converts_pptx_artifact_to_pdf(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    user, workspace, conversation = _user_workspace_conversation(db)
    _fake_libreoffice(monkeypatch)

    try:
        result = invoke_tool(
            db,
            user,
            "artifact.create_pptx",
            {
                "workspace_id": workspace.id,
                "conversation_id": conversation.id,
                "title": "PPT 工作区预览",
                "body": "第一页\n第二页",
            },
        )["result"]
        node_id = f"artifact:{result['artifact_id']}"

        preview = asyncio.run(preview_workspace_file(workspace.id, node_id, db, user))["data"]
        pdf = asyncio.run(download_workspace_file_preview_pdf(workspace.id, node_id, db, user))

        assert preview["mode"] == "pdf"
        assert preview["content_type"] == "application/pdf"
        assert pdf.media_type == "application/pdf"
    finally:
        _cleanup(workspace.id)


def test_workspace_file_preview_converts_xlsx_artifact_to_pdf(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    user, workspace, conversation = _user_workspace_conversation(db)
    _fake_libreoffice(monkeypatch)

    try:
        result = invoke_tool(
            db,
            user,
            "artifact.create_xlsx",
            {
                "workspace_id": workspace.id,
                "conversation_id": conversation.id,
                "title": "Excel 工作区预览",
                "body": "名称,数量\nAgentHub,1",
            },
        )["result"]
        node_id = f"artifact:{result['artifact_id']}"

        preview = asyncio.run(preview_workspace_file(workspace.id, node_id, db, user))["data"]
        pdf = asyncio.run(download_workspace_file_preview_pdf(workspace.id, node_id, db, user))

        assert preview["mode"] == "pdf"
        assert preview["preview_pdf_url"]
        assert pdf.media_type == "application/pdf"
    finally:
        _cleanup(workspace.id)


def test_workspace_file_preview_falls_back_to_text_pdf_when_libreoffice_missing(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user, workspace, conversation = _user_workspace_conversation(db)
    monkeypatch.setattr(office_preview, "_find_soffice", lambda: None)

    try:
        result = invoke_tool(
            db,
            user,
            "artifact.create_docx",
            {
                "workspace_id": workspace.id,
                "conversation_id": conversation.id,
                "title": "No LibreOffice",
                "body": "fallback text",
            },
        )["result"]
        node_id = f"artifact:{result['artifact_id']}"

        preview = asyncio.run(preview_workspace_file(workspace.id, node_id, db, user))["data"]
        pdf = asyncio.run(download_workspace_file_preview_pdf(workspace.id, node_id, db, user))
        downloaded = asyncio.run(download_workspace_file(workspace.id, node_id, db, user))

        assert preview["mode"] == "pdf"
        assert "LibreOffice" in preview["office_preview"]["warning"]
        assert pdf.media_type == "application/pdf"
        assert pdf.path.endswith("preview.pdf")
        assert downloaded.media_type.startswith("application/vnd.openxmlformats-officedocument")
    finally:
        _cleanup(workspace.id)


def test_workspace_file_preview_supports_legacy_artifact_html(db: Session) -> None:
    user, workspace, conversation = _user_workspace_conversation(db)
    artifact = Artifact(
        conversation_id=conversation.id,
        type="web_app",
        name="旧版 HTML 页面",
        mime_type="text/html",
        content={"files": {"index.html": "<!doctype html><h1>旧版 HTML 页面</h1>"}},
    )
    db.add(artifact)
    db.commit()

    try:
        preview = asyncio.run(preview_workspace_file(workspace.id, f"artifact:{artifact.id}", db, user))["data"]

        assert preview["mode"] == "html"
        assert "旧版 HTML 页面" in preview["text"]
        assert preview["artifact_id"] == artifact.id
    finally:
        _cleanup(workspace.id)


def test_workspace_file_preview_converts_legacy_docx_artifact_to_pdf(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    user, workspace, conversation = _user_workspace_conversation(db)
    _fake_libreoffice(monkeypatch)
    artifact = Artifact(
        conversation_id=conversation.id,
        type="document",
        name="旧版 Word 文档",
        mime_type="text/html",
        content={
            "tool_output": {"format": "docx"},
            "files": {"index.html": "<article><h1>旧版 Word 文档</h1><p>可预览正文</p></article>"},
        },
    )
    db.add(artifact)
    db.commit()

    try:
        preview = asyncio.run(preview_workspace_file(workspace.id, f"artifact:{artifact.id}", db, user))["data"]
        tree = workspace_file_tree(db, user, workspace.id)
        flat = _flatten(tree["root"])
        folder = next(
            item
            for item in flat
            if item.get("path") == f"artifacts/conversations/{conversation.id}/{artifact.id}"
        )

        assert preview["mode"] == "pdf"
        assert preview["preview_pdf_url"]
        assert folder["display_name"] == f"产物：旧版 Word 文档 · {artifact.id[:8]}"
    finally:
        _cleanup(workspace.id)


def test_workspace_file_preview_handles_text_markdown_json_and_binary(db: Session) -> None:
    user, workspace, _conversation = _user_workspace_conversation(db)
    root = workspace_root(workspace.id) / "files"
    root.mkdir(parents=True, exist_ok=True)
    markdown = root / "说明.md"
    json_file = root / "data.json"
    text_file = root / "notes.txt"
    binary = root / "archive.bin"
    markdown.write_text("# 标题\n正文", encoding="utf-8")
    json_file.write_text('{"name": "AgentHub"}', encoding="utf-8")
    text_file.write_text("普通文本", encoding="utf-8")
    binary.write_bytes(b"\x00\x01\x02\x03")

    try:
        markdown_payload = asyncio.run(
            preview_workspace_file(workspace.id, f"fs:{quote('files/说明.md', safe='')}", db, user)
        )["data"]
        json_payload = asyncio.run(
            preview_workspace_file(workspace.id, f"fs:{quote('files/data.json', safe='')}", db, user)
        )["data"]
        text_payload = asyncio.run(
            preview_workspace_file(workspace.id, f"fs:{quote('files/notes.txt', safe='')}", db, user)
        )["data"]
        binary_payload = asyncio.run(
            preview_workspace_file(workspace.id, f"fs:{quote('files/archive.bin', safe='')}", db, user)
        )["data"]

        assert markdown_payload["mode"] == "text"
        assert "AgentHub" in json_payload["text"]
        assert "普通文本" in text_payload["text"]
        assert binary_payload["mode"] == "binary"
        assert binary_payload["text"] == ""
    finally:
        _cleanup(workspace.id)


def test_workspace_artifact_directory_display_name_uses_artifact_name(db: Session) -> None:
    user, workspace, conversation = _user_workspace_conversation(db)

    try:
        result = invoke_tool(
            db,
            user,
            "artifact.create_html",
            {
                "workspace_id": workspace.id,
                "conversation_id": conversation.id,
                "title": "HTML 示例演示页面",
                "html": "<!doctype html><h1>HTML 示例演示页面</h1>",
            },
        )["result"]
        tree = workspace_file_tree(db, user, workspace.id)
        flat = _flatten(tree["root"])
        display_names = {str(item.get("display_name") or "") for item in flat}
        file_node = next(item for item in flat if item.get("id") == f"artifact:{result['artifact_id']}")

        assert result["artifact_id"] not in display_names
        assert f"产物：HTML 示例演示页面 · {result['artifact_id'][:8]}" in display_names
        assert result["artifact_id"] not in str(file_node.get("display_path"))
        assert "产物：HTML 示例演示页面" in str(file_node.get("display_path"))
    finally:
        _cleanup(workspace.id)


def test_workspace_file_operations_create_move_favorite_and_bulk_delete(db: Session) -> None:
    user, workspace, _conversation = _user_workspace_conversation(db)
    source = workspace_root(workspace.id) / "files" / "draft.txt"
    source.write_text("draft", encoding="utf-8")
    node_id = "fs:files%2Fdraft.txt"

    try:
        created = create_workspace_folder(db, user, workspace.id, "files", "方案资料")
        moved = move_workspace_file_nodes(db, user, workspace.id, [node_id], created["path"])
        moved_node = next(
            item["id"]
            for item in _flatten(workspace_file_tree(db, user, workspace.id)["root"])
            if item.get("path") == f"{created['path']}/draft.txt"
        )
        set_workspace_file_favorite(db, user, workspace.id, moved_node, True)
        tree = workspace_file_tree(db, user, workspace.id)
        flat = _flatten(tree["root"])

        assert moved["moved"][0]["path"] == f"{created['path']}/draft.txt"
        assert any(item["id"] == moved_node and item["favorite"] for item in flat)
        assert tree["stats"]["file_count"] >= 1

        deleted = bulk_delete_workspace_file_nodes(db, user, workspace.id, [moved_node])
        assert deleted["deleted"] == [moved_node]
        assert not (workspace_root(workspace.id) / created["path"] / "draft.txt").exists()
    finally:
        _cleanup(workspace.id)


def test_workspace_html_preview_returns_raw_html() -> None:
    path = workspace_root("preview-test") / "files" / "HTML示例演示页面.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("<!doctype html><html><body><h1>HTML示例演示页面</h1></body></html>", encoding="utf-8")

    try:
        payload = preview_payload(path, content_type="text/html", filename=path.name)

        assert payload["mode"] == "html"
        assert "<h1>HTML示例演示页面</h1>" in payload["text"]
    finally:
        _cleanup("preview-test")


def test_at_file_reference_is_resolved_into_message_attachment(db: Session) -> None:
    user, workspace, conversation = _user_workspace_conversation(db)
    path = scoped_dir(workspace.id, "sandbox", conversation_id=conversation.id) / "summary.md"
    path.write_text("# Summary\nAgentHub workspace context", encoding="utf-8")

    try:
        message = _send(
            db,
            user,
            conversation.id,
            {"content": {"text": "请总结 @file(sandbox/conversations/%s/summary.md)" % conversation.id}},
            trigger_agent=False,
        )
        attachments = message.content["attachments"]

        assert attachments[0]["filename"] == "summary.md"
        assert "AgentHub workspace context" in attachments[0]["extracted_text"]
        assert attachments[0]["metadata"]["reference_type"] == "workspace_file"
    finally:
        _cleanup(workspace.id)


def test_at_file_reference_missing_file_reports_clear_error(db: Session) -> None:
    user, workspace, conversation = _user_workspace_conversation(db)

    try:
        with pytest.raises(ValidationAppError, match="文件引用不存在"):
            _send(
                db,
                user,
                conversation.id,
                {"content": {"text": "请总结 @file(sandbox/missing.md)"}},
                trigger_agent=False,
            )
    finally:
        _cleanup(workspace.id)


def test_workspace_file_rename_updates_file_asset_display_name(db: Session) -> None:
    user, workspace, conversation = _user_workspace_conversation(db)
    path = scoped_dir(workspace.id, "uploads", conversation_id=conversation.id) / "old.txt"
    path.write_text("hello", encoding="utf-8")
    asset = FileAsset(
        owner_id=user.id,
        conversation_id=conversation.id,
        filename="old.txt",
        original_filename="old.txt",
        content_type="text/plain",
        size=path.stat().st_size,
        checksum="rename-checksum",
        storage_path=str(path),
        purpose="attachment",
        parse_status="parsed",
        extra={"workspace_id": workspace.id},
    )
    db.add(asset)
    db.commit()

    try:
        result = rename_workspace_file_node(db, user, workspace.id, f"file:{asset.id}", "renamed.txt")
        db.refresh(asset)

        assert result["display_name"] == "renamed.txt"
        assert asset.original_filename == "renamed.txt"
        assert "renamed.txt" in {item["display_name"] for item in _flatten(workspace_file_tree(db, user, workspace.id)["root"])}
    finally:
        _cleanup(workspace.id)


def test_workspace_file_tree_isolation_and_delete_permissions(db: Session) -> None:
    owner = _user()
    other = _user()
    workspace_a = _workspace(owner, "tree-a")
    workspace_b = _workspace(owner, "tree-b")
    conversation_a = Conversation(
        creator_id=owner.id,
        chat_type="single",
        title="A",
        extra={"workspace_id": workspace_a.id},
    )
    db.add_all([owner, other, workspace_a, workspace_b, conversation_a])
    db.commit()
    path = scoped_dir(workspace_a.id, "uploads", conversation_id=conversation_a.id) / "secret.txt"
    path.write_text("workspace-a-only", encoding="utf-8")
    asset = FileAsset(
        owner_id=owner.id,
        conversation_id=conversation_a.id,
        filename="secret.txt",
        original_filename="secret.txt",
        content_type="text/plain",
        size=path.stat().st_size,
        checksum="secret-checksum",
        storage_path=str(path),
        purpose="attachment",
        parse_status="parsed",
        extra={"workspace_id": workspace_a.id},
    )
    db.add(asset)
    db.commit()

    try:
        assert "secret.txt" in {item["name"] for item in _flatten(workspace_file_tree(db, owner, workspace_a.id)["root"])}
        assert "secret.txt" not in {item["name"] for item in _flatten(workspace_file_tree(db, owner, workspace_b.id)["root"])}

        with pytest.raises(Exception):
            workspace_file_tree(db, other, workspace_a.id)

        db.add(WorkspaceMember(workspace_id=workspace_a.id, user_id=other.id, role="member", permissions=["files:read"]))
        db.commit()
        assert "secret.txt" in {item["name"] for item in _flatten(workspace_file_tree(db, other, workspace_a.id)["root"])}

        deleted = delete_workspace_file_node(db, owner, workspace_a.id, f"file:{asset.id}")
        assert deleted["deleted"] is True
        db.refresh(asset)
        assert asset.deleted_at is not None
    finally:
        _cleanup(workspace_a.id, workspace_b.id)


def test_dangerous_sandbox_command_is_rejected_and_recorded(db: Session) -> None:
    user, workspace, conversation = _user_workspace_conversation(db)

    try:
        with pytest.raises(ValidationAppError):
            invoke_tool(
                db,
                user,
                "sandbox.run",
                {"workspace_id": workspace.id, "conversation_id": conversation.id, "command": "rm -rf ."},
            )
        invocation = db.scalar(
            select(ToolInvocation)
            .where(ToolInvocation.tool_name == "sandbox.run")
            .order_by(ToolInvocation.created_at.desc())
        )

        assert invocation is not None
        assert invocation.workspace_id == workspace.id
        assert invocation.status == "failed"
    finally:
        _cleanup(workspace.id)


def test_message_python_code_block_runs_in_conversation_sandbox(db: Session) -> None:
    user, workspace, conversation = _user_workspace_conversation(db)
    message = Message(
        conversation_id=conversation.id,
        sender_type="agent",
        sender_id="agent-code",
        sender_name="Code Agent",
        content_type="text",
        content={"text": "```python\nprint('hello from code')\n```"},
        status="completed",
    )
    db.add(message)
    db.commit()

    try:
        result = run_message_code_block(
            db,
            user=user,
            conversation_id=conversation.id,
            message_id=message.id,
            language="python",
            code="print('hello from code')",
            index=0,
            workspace_id=workspace.id,
        )
        db.refresh(message)
        invocation = db.scalar(
            select(ToolInvocation)
            .where(ToolInvocation.tool_name == "sandbox.run")
            .order_by(ToolInvocation.created_at.desc())
        )

        assert result["status"] == "succeeded"
        assert result["exit_code"] == 0
        assert "hello from code" in result["stdout"]
        assert invocation is not None
        assert invocation.status == "succeeded"
        assert message.content["code_runs"]["0"]["exit_code"] == 0
    finally:
        _cleanup(workspace.id)


def test_message_interactive_python_code_is_rejected_without_hanging(db: Session) -> None:
    user, workspace, conversation = _user_workspace_conversation(db)
    message = Message(
        conversation_id=conversation.id,
        sender_type="agent",
        sender_id="agent-code",
        sender_name="Code Agent",
        content_type="text",
        content={"text": "```python\nname = input('name: ')\n```"},
        status="completed",
    )
    db.add(message)
    db.commit()

    try:
        result = run_message_code_block(
            db,
            user=user,
            conversation_id=conversation.id,
            message_id=message.id,
            language="python",
            code="name = input('name: ')",
            index=0,
            workspace_id=workspace.id,
        )

        assert result["status"] == "failed"
        assert result["exit_code"] == -1
        assert "input()" in result["stderr"]
    finally:
        _cleanup(workspace.id)


def _user_workspace_conversation(db: Session) -> tuple[User, Workspace, Conversation]:
    user = _user()
    workspace = _workspace(user, "main")
    conversation = Conversation(
        creator_id=user.id,
        chat_type="single",
        title="Workspace Sandbox",
        extra={"workspace_id": workspace.id},
    )
    db.add_all([user, workspace, conversation])
    db.commit()
    return user, workspace, conversation


def _user() -> User:
    suffix = uuid.uuid4().hex[:8]
    return User(
        id=f"user-{suffix}",
        email=f"sandbox-{suffix}@example.com",
        username=f"sandbox-{suffix}",
        password_hash="x",
        display_name="Sandbox User",
    )


def _workspace(user: User, suffix: str) -> Workspace:
    return Workspace(
        id=f"ws-{suffix}-{uuid.uuid4().hex[:8]}",
        owner_id=user.id,
        name=f"Workspace {suffix}",
    )


def _cleanup(*workspace_ids: Any) -> None:
    for workspace_id in workspace_ids:
        shutil.rmtree(workspace_root(str(workspace_id)), ignore_errors=True)


def _fake_libreoffice(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    calls: list[list[str]] = []
    monkeypatch.setattr(office_preview, "_find_soffice", lambda: "soffice")

    def fake_run(
        command: list[str],
        *,
        capture_output: bool,
        text: bool,
        encoding: str,
        errors: str,
        timeout: int,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        out_dir = Path(command[command.index("--outdir") + 1])
        source = Path(command[-1])
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"{source.stem}.pdf").write_bytes(b"%PDF-1.4\n% fake office preview\n")
        return subprocess.CompletedProcess(command, 0, stdout="converted", stderr="")

    monkeypatch.setattr(office_preview.subprocess, "run", fake_run)
    return calls


def _flatten(node: dict[str, Any]) -> list[dict[str, Any]]:
    items = [node]
    for child in node.get("children") or []:
        items.extend(_flatten(child))
    return items
