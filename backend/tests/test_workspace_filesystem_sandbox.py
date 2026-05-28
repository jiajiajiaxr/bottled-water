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
from app.models import Conversation, SandboxSession, ToolInvocation, User, Workspace
from app.services.tools.executor import invoke_tool
from app.services.workspaces.filesystem import workspace_root


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
        "path": "note.txt",
        "content": "hello-workspace",
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
                "command": "python -c \"print(open('note.txt', encoding='utf-8').read())\"",
                "timeout": 5,
            },
        )
        session = db.scalar(select(SandboxSession).where(SandboxSession.workspace_id == workspace.id))

        assert written["result"]["status"] == "succeeded"
        assert result["result"]["status"] == "succeeded"
        assert "hello-workspace" in result["result"]["stdout"]
        assert session is not None
        assert session.command_history[0]["cwd"] == result["result"]["cwd"]
        assert any(item["path"] == "note.txt" for item in session.mounted_files)
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
