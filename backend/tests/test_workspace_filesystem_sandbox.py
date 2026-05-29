from __future__ import annotations

import shutil
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import Base
from app.core.errors import ValidationAppError
from app.models import Conversation, FileAsset, SandboxSession, ToolInvocation, User, Workspace, WorkspaceMember
from app.api.messages import _send
from app.services.files.workspace_tree import delete_workspace_file_node, rename_workspace_file_node, workspace_file_tree
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
        assert any(str(name).startswith("Workspace Sandbox · ") for name in names)
        assert all(item.get("display_name") for item in flat)
    finally:
        _cleanup(workspace.id)


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


def _flatten(node: dict[str, Any]) -> list[dict[str, Any]]:
    items = [node]
    for child in node.get("children") or []:
        items.extend(_flatten(child))
    return items
