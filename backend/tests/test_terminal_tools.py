from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.errors import ValidationAppError
from app.api.sandbox import (
    send_terminal_input,
    start_terminal,
    terminal_snapshot,
    wait_terminal_output,
)
from app.schemas.requests import TerminalSendRequest, TerminalStartRequest, TerminalWaitRequest
from app.services.tools.executor import invoke_tool
from db.base import Base
from db.models import Conversation, SandboxSession, ToolInvocation, User, Workspace


def test_terminal_tools_drive_interactive_process(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _redirect_workspace_var(tmp_path, monkeypatch)
    db = _memory_session()
    user, workspace, conversation = _seed_workspace(db)
    script_dir = tmp_path / "var" / "workspaces" / workspace.id / "sandbox" / "conversations" / conversation.id
    script_dir.mkdir(parents=True)
    (script_dir / "ask.py").write_text(
        "\n".join(
            [
                "from pathlib import Path",
                "import sys",
                "print('Project name?', end=' ', flush=True)",
                "name = sys.stdin.readline().strip()",
                "Path('answer.txt').write_text(name, encoding='utf-8')",
                "print('Created ' + name, flush=True)",
            ]
        ),
        encoding="utf-8",
    )

    started = invoke_tool(
        db,
        user,
        "terminal.start",
        {
            "workspace_id": workspace.id,
            "conversation_id": conversation.id,
            "command": "python ask.py",
            "timeout": 10,
        },
    )
    session_id = started["result"]["session_id"]
    prompt = invoke_tool(
        db,
        user,
        "terminal.wait_for",
        {"session_id": session_id, "patterns": ["Project name?"], "timeout_ms": 3000},
    )
    sent = invoke_tool(db, user, "terminal.send", {"session_id": session_id, "input": "demo-app\n"})
    finished = invoke_tool(
        db,
        user,
        "terminal.wait_for",
        {"session_id": session_id, "patterns": ["Created demo-app"], "timeout_ms": 3000},
    )
    snapshot = invoke_tool(db, user, "terminal.snapshot", {"session_id": session_id})
    invocations = db.scalars(select(ToolInvocation).order_by(ToolInvocation.created_at)).all()

    assert started["result"]["status"] == "succeeded"
    assert started["result"]["capability_level"] == "interactive"
    assert prompt["result"]["matched"] is True
    assert sent["result"]["status"] == "succeeded"
    assert finished["result"]["matched"] is True
    assert snapshot["result"]["session_status"] == "completed"
    assert snapshot["result"]["exit_code"] == 0
    assert "Created demo-app" in snapshot["result"]["stdout_tail"]
    assert (script_dir / "answer.txt").read_text(encoding="utf-8") == "demo-app"
    assert {item.tool_name for item in invocations} >= {
        "terminal.start",
        "terminal.wait_for",
        "terminal.send",
        "terminal.snapshot",
    }
    assert all(item.status == "succeeded" for item in invocations)


def test_terminal_rejects_dangerous_command() -> None:
    db = _memory_session()
    user = User(
        id="user-terminal",
        email="terminal@example.com",
        username="terminal",
        password_hash="x",
        role="admin",
    )
    db.add(user)
    db.commit()

    with pytest.raises(ValidationAppError):
        invoke_tool(db, user, "terminal.start", {"command": "rm -rf ."})

    invocation = db.scalar(select(ToolInvocation).where(ToolInvocation.tool_name == "terminal.start"))
    assert invocation is not None
    assert invocation.status == "failed"


def test_terminal_wait_timeout_keeps_session_running(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _redirect_workspace_var(tmp_path, monkeypatch)
    db = _memory_session()
    user, workspace, conversation = _seed_workspace(db)
    script_dir = tmp_path / "var" / "workspaces" / workspace.id / "sandbox" / "conversations" / conversation.id
    script_dir.mkdir(parents=True)
    (script_dir / "slow.py").write_text(
        "\n".join(
            [
                "import time",
                "print('Ready', flush=True)",
                "time.sleep(5)",
            ]
        ),
        encoding="utf-8",
    )

    started = invoke_tool(
        db,
        user,
        "terminal.start",
        {
            "workspace_id": workspace.id,
            "conversation_id": conversation.id,
            "command": "python slow.py",
            "timeout": 10,
        },
    )
    session_id = started["result"]["session_id"]

    timed_out = invoke_tool(
        db,
        user,
        "terminal.wait_for",
        {"session_id": session_id, "patterns": ["Never printed"], "timeout_ms": 200},
    )
    stopped = invoke_tool(db, user, "terminal.stop", {"session_id": session_id})
    timeout_invocation = db.scalar(
        select(ToolInvocation)
        .where(ToolInvocation.tool_name == "terminal.wait_for", ToolInvocation.status == "timeout")
        .order_by(ToolInvocation.created_at.desc())
    )

    assert timed_out["result"]["status"] == "timeout"
    assert timed_out["result"]["session_status"] == "running"
    assert stopped["result"]["session_status"] == "cancelled"
    assert timeout_invocation is not None


def test_terminal_uses_existing_sandbox_workspace_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _redirect_workspace_var(tmp_path, monkeypatch)
    db = _memory_session()
    user, workspace, _conversation = _seed_workspace(db)
    sandbox = SandboxSession(
        id="sandbox-terminal-root",
        owner_id=user.id,
        workspace_id=workspace.id,
        name="Existing Sandbox",
        image="local-python-node",
        status="ready",
        extra={"filesystem_workspace_id": workspace.id},
    )
    db.add(sandbox)
    db.commit()
    script_dir = tmp_path / "var" / "workspaces" / workspace.id / "sandbox"
    script_dir.mkdir(parents=True)
    (script_dir / "root_check.py").write_text(
        "from pathlib import Path\nPath('root-ok.txt').write_text('ok', encoding='utf-8')\nprint('root ok', flush=True)\n",
        encoding="utf-8",
    )

    started = invoke_tool(
        db,
        user,
        "terminal.start",
        {
            "sandbox_id": sandbox.id,
            "command": "python root_check.py",
            "timeout": 10,
        },
    )
    session_id = started["result"]["session_id"]
    finished = invoke_tool(
        db,
        user,
        "terminal.wait_for",
        {"session_id": session_id, "patterns": ["root ok"], "timeout_ms": 3000},
    )

    assert finished["result"]["matched"] is True
    assert (script_dir / "root-ok.txt").read_text(encoding="utf-8") == "ok"
    assert not (tmp_path / "var" / "workspaces" / "default" / "sandbox" / "root-ok.txt").exists()


@pytest.mark.asyncio
async def test_terminal_api_endpoints_persist_tool_invocations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _redirect_workspace_var(tmp_path, monkeypatch)
    session_factory = await _async_memory_session_factory()
    async with session_factory() as db:
        user = User(
            id="user-terminal-api",
            email="terminal-api@example.com",
            username="terminal-api",
            password_hash="x",
            display_name="Terminal API User",
            role="admin",
        )
        workspace = Workspace(
            id="workspace-terminal-api",
            owner_id=user.id,
            name="Terminal API Workspace",
        )
        db.add_all([user, workspace])
        await db.commit()
        script_dir = tmp_path / "var" / "workspaces" / workspace.id / "sandbox"
        script_dir.mkdir(parents=True)
        (script_dir / "ask_api.py").write_text(
            "\n".join(
                [
                    "import sys",
                    "print('Name?', flush=True)",
                    "name = sys.stdin.readline().strip()",
                    "print('Hi ' + name, flush=True)",
                ]
            ),
            encoding="utf-8",
        )

        started = await start_terminal(
            TerminalStartRequest(
                workspace_id=workspace.id,
                command="python ask_api.py",
                timeout_seconds=10,
            ),
            db=db,
            user=user,
        )
        session_id = started["data"]["session_id"]
        waited = await wait_terminal_output(
            session_id,
            TerminalWaitRequest(patterns=["Name?"], timeout_ms=3000),
            db=db,
            user=user,
        )
        sent = await send_terminal_input(
            session_id,
            TerminalSendRequest(input="AgentHub\n"),
            db=db,
            user=user,
        )
        snapshot = await terminal_snapshot(session_id, db=db, user=user)
        await wait_terminal_output(
            session_id,
            TerminalWaitRequest(patterns=["Hi AgentHub"], timeout_ms=3000),
            db=db,
            user=user,
        )

        invocations = (
            await db.scalars(select(ToolInvocation).order_by(ToolInvocation.created_at))
        ).all()

        assert waited["data"]["matched"] is True
        assert sent["data"]["session_id"] == session_id
        assert snapshot["data"]["session_id"] == session_id
        assert {item.tool_name for item in invocations} >= {
            "terminal.start",
            "terminal.wait_for",
            "terminal.send",
            "terminal.snapshot",
        }
        assert all(item.result for item in invocations)


def _memory_session() -> Any:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return session_factory()


async def _async_memory_session_factory() -> Any:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        future=True,
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return async_sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def _seed_workspace(db: Any) -> tuple[User, Workspace, Conversation]:
    user = User(
        id="user-terminal",
        email="terminal@example.com",
        username="terminal",
        password_hash="x",
        display_name="Terminal User",
        role="admin",
    )
    workspace = Workspace(id="workspace-terminal", owner_id=user.id, name="Terminal Workspace")
    conversation = Conversation(
        id="conversation-terminal",
        creator_id=user.id,
        chat_type="single",
        title="Terminal Chat",
        extra={"workspace_id": workspace.id},
    )
    db.add_all([user, workspace, conversation])
    db.commit()
    return user, workspace, conversation


def _redirect_workspace_var(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import app.services.workspaces.filesystem as filesystem

    monkeypatch.setattr(filesystem, "backend_var_dir", lambda: tmp_path / "var")
