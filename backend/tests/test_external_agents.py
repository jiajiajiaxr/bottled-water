from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.errors import ValidationAppError
from app.services.agents.tool_loop import build_tools_for_agent, execute_tool_by_name
from app.services.external_agents.registry import get_external_agent_adapter
from app.services.external_agents.workspace import external_agent_cwd
from app.services.tools.catalog import list_tools, sync_builtin_tool_definitions
from app.services.tools.executor import invoke_tool
from db.base import Base
from app.services.workflows.graph import Node
from app.services.workflows.nodes.base import WorkflowExecutionContext
from app.services.workflows.nodes.tool import ToolNodeExecutor
from db.models import (
    Agent,
    Conversation,
    ExternalAgentRun,
    Message,
    Task,
    ToolDefinition,
    ToolInvocation,
    User,
    WorkflowRun,
    Workspace,
)


def test_probe_codex_missing_returns_degraded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CODEX_CLI_PATH", raising=False)
    monkeypatch.setenv("PATH", "")

    probe = get_external_agent_adapter("codex").probe()

    assert probe.installed is False
    assert probe.reason == "command_not_found"
    assert probe.setup_hint


def test_probe_payload_redacts_resolved_command_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CODEX_CLI_PATH", sys.executable)

    probe = get_external_agent_adapter("codex").probe()
    payload = probe.to_dict()

    assert probe.installed is True
    assert probe.command_path == sys.executable
    assert "command_path" not in payload
    assert payload["command_source"] == "env:CODEX_CLI_PATH"


def test_fake_codex_run_persists_events_and_changed_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _redirect_workspace_var(tmp_path, monkeypatch)
    fake_cli = _fake_cli(tmp_path, exit_code=0)
    monkeypatch.setenv("CODEX_CLI_PATH", sys.executable)
    monkeypatch.setenv("CODEX_CLI_TEMPLATE", json.dumps(["{command}", str(fake_cli), "{prompt}"]))
    db = _memory_session()
    user, workspace, conversation = _seed_workspace(db)

    payload = invoke_tool(
        db,
        user,
        "external_agent.invoke",
        {
            "action": "run",
            "provider": "codex",
            "workspace_id": workspace.id,
            "conversation_id": conversation.id,
            "prompt": "实现一个排序函数",
            "timeout_ms": 10_000,
        },
    )
    result = payload["result"]
    run = db.get(ExternalAgentRun, result["run_id"])
    invocation = db.get(ToolInvocation, payload["invocation_id"])

    assert result["status"] == "completed"
    assert result["provider"] == "codex"
    assert result["exit_code"] == 0
    assert "fake external agent received" in result["stdout_tail"]
    assert result["changed_files"][0]["path"] == "agent_output.txt"
    assert "absolute_path" not in result["changed_files"][0]
    assert run is not None
    assert run.status == "completed"
    assert run.workspace_id == workspace.id
    assert invocation is not None
    assert invocation.tool_name == "external_agent.invoke"
    assert invocation.status == "completed"


def test_legacy_external_agent_run_aliases_to_invoke(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _redirect_workspace_var(tmp_path, monkeypatch)
    fake_cli = _fake_cli(tmp_path, exit_code=0)
    monkeypatch.setenv("CODEX_CLI_PATH", sys.executable)
    monkeypatch.setenv("CODEX_CLI_TEMPLATE", json.dumps(["{command}", str(fake_cli), "{prompt}"]))
    db = _memory_session()
    user, workspace, _conversation = _seed_workspace(db)

    payload = invoke_tool(
        db,
        user,
        "external_agent.run_codex",
        {
            "workspace_id": workspace.id,
            "prompt": "legacy run",
            "timeout_ms": 10_000,
        },
    )

    assert payload["tool"]["name"] == "external_agent.invoke"
    assert payload["result"]["provider"] == "codex"
    invocation = db.get(ToolInvocation, payload["invocation_id"])
    assert invocation is not None
    assert invocation.tool_name == "external_agent.invoke"


def test_fake_claude_code_failure_is_recorded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _redirect_workspace_var(tmp_path, monkeypatch)
    fake_cli = _fake_cli(tmp_path, exit_code=7, stderr_text="boom secret=sk-test")
    monkeypatch.setenv("CLAUDE_CODE_CLI_PATH", sys.executable)
    monkeypatch.setenv("CLAUDE_CODE_CLI_TEMPLATE", json.dumps(["{command}", str(fake_cli), "{prompt}"]))
    db = _memory_session()
    user, workspace, conversation = _seed_workspace(db)

    payload = invoke_tool(
        db,
        user,
        "external_agent.invoke",
        {
            "action": "run",
            "provider": "claude_code",
            "workspace_id": workspace.id,
            "conversation_id": conversation.id,
            "prompt": "修复测试",
            "timeout_ms": 10_000,
        },
    )
    result = payload["result"]

    assert result["status"] == "failed"
    assert result["provider"] == "claude_code"
    assert result["exit_code"] == 7
    assert "sk-test" not in result["stderr_tail"]
    assert "boom" in result["stderr_tail"]
    assert db.scalar(select(ExternalAgentRun)).status == "failed"


def test_external_agent_cancel_converges_to_cancelled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _redirect_workspace_var(tmp_path, monkeypatch)
    fake_cli = _sleeping_cli(tmp_path)
    monkeypatch.setenv("CODEX_CLI_PATH", sys.executable)
    monkeypatch.setenv("CODEX_CLI_TEMPLATE", json.dumps(["{command}", str(fake_cli), "{prompt}"]))
    db = _memory_session()
    user, workspace, conversation = _seed_workspace(db)
    started = invoke_tool(
        db,
        user,
        "external_agent.invoke",
        {
            "action": "run",
            "provider": "codex",
            "workspace_id": workspace.id,
            "conversation_id": conversation.id,
            "prompt": "长任务",
            "wait": False,
        },
    )["result"]

    cancelled = invoke_tool(
        db,
        user,
        "external_agent.invoke",
        {"action": "cancel", "run_id": started["run_id"]},
    )["result"]

    assert cancelled["status"] == "cancelled"
    assert db.get(ExternalAgentRun, started["run_id"]).status == "cancelled"


def test_external_agent_cwd_escape_is_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _redirect_workspace_var(tmp_path, monkeypatch)
    db = _memory_session()
    _user, workspace, conversation = _seed_workspace(db)

    with pytest.raises(ValidationAppError):
        external_agent_cwd(
            db,
            {
                "workspace_id": workspace.id,
                "conversation_id": conversation.id,
                "cwd": "../outside",
            },
            provider="codex",
        )


def test_external_tools_sync_and_agent_authorization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _redirect_workspace_var(tmp_path, monkeypatch)
    fake_cli = _fake_cli(tmp_path)
    monkeypatch.setenv("CODEX_CLI_PATH", sys.executable)
    monkeypatch.setenv("CODEX_CLI_TEMPLATE", json.dumps(["{command}", str(fake_cli), "{prompt}"]))
    db = _memory_session()
    user, workspace, conversation = _seed_workspace(db)
    authorized_agent = Agent(
        id="agent-auth",
        owner_id=user.id,
        name="Authorized Agent",
        type="custom",
        config={"tools": ["external_agent.invoke"]},
    )
    unauthorized_agent = Agent(
        id="agent-denied",
        owner_id=user.id,
        name="Denied Agent",
        type="custom",
        config={"tools": [], "capability_permissions_initialized": True},
    )
    db.add_all([authorized_agent, unauthorized_agent])
    sync_builtin_tool_definitions(db)
    db.commit()

    tool_names = {item["function"]["name"] for item in build_tools_for_agent(db, authorized_agent)}
    denied = asyncio.run(
        execute_tool_by_name(
            db,
            agent=unauthorized_agent,
            user=user,
            conversation=conversation,
            tool_name="external_agent.run_codex",
            arguments={"workspace_id": workspace.id, "prompt": "should not run"},
        )
    )
    allowed = asyncio.run(
        execute_tool_by_name(
            db,
            agent=authorized_agent,
            user=user,
            conversation=conversation,
            tool_name="external_agent.run_codex",
            arguments={"workspace_id": workspace.id, "prompt": "run it"},
        )
    )

    assert "external_agent.invoke" in tool_names
    assert "external_agent.run_codex" not in tool_names
    assert db.scalar(select(ToolDefinition).where(ToolDefinition.name == "external_agent.invoke")) is not None
    assert db.scalar(select(ToolDefinition).where(ToolDefinition.name == "external_agent.run_codex")) is None
    assert denied["status"] == "failed"
    assert "未授权" in denied["output"] or "Agent" in denied["output"]
    assert allowed["status"] == "completed"
    assert allowed["output"]["run_id"]


def test_tool_catalog_exposes_unified_external_agent_only() -> None:
    db = _memory_session()
    user, _workspace, _conversation = _seed_workspace(db)

    items = list_tools(db, user)
    names = {item["name"] for item in items}
    unified = next(item for item in items if item["name"] == "external_agent.invoke")

    assert "external_agent.invoke" in names
    assert unified["display_name"] == "调用外部智能体"
    assert "opencode" in json.dumps(unified["input_schema"], ensure_ascii=False)
    assert "external_agent.probe" not in names
    assert "external_agent.run_codex" not in names
    assert "external_agent.run_claude_code" not in names
    assert "external_agent.cancel" not in names


def test_workflow_tool_node_can_run_external_agent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _redirect_workspace_var(tmp_path, monkeypatch)
    fake_cli = _fake_cli(tmp_path)
    monkeypatch.setenv("CODEX_CLI_PATH", sys.executable)
    monkeypatch.setenv("CODEX_CLI_TEMPLATE", json.dumps(["{command}", str(fake_cli), "{prompt}"]))
    db = _memory_session()
    user, workspace, conversation = _seed_workspace(db)
    agent = Agent(
        id="agent-workflow",
        owner_id=user.id,
        name="Workflow Agent",
        type="custom",
        config={"tools": ["external_agent.invoke"]},
    )
    message = Message(
        id="message-workflow",
        conversation_id=conversation.id,
        sender_type="user",
        sender_id=user.id,
        sender_name=user.display_name,
        content={"text": "请实现功能"},
    )
    task = Task(id="task-workflow", conversation_id=conversation.id, creator_id=user.id, title="Workflow task")
    workflow_run = WorkflowRun(
        id="workflow-run-external",
        conversation_id=conversation.id,
        trigger_message_id=message.id,
        started_by=user.id,
        status="running",
    )
    db.add_all([agent, message, task, workflow_run])
    sync_builtin_tool_definitions(db)
    db.commit()
    node = Node(
        id="node-tool",
        type="tool",
        title="Run Codex",
        config={
            "tool_name": "external_agent.invoke",
            "arguments": {
                "action": "run",
                "provider": "codex",
                "workspace_id": workspace.id,
                "prompt": "{{input}}",
            },
        },
        agent_id=agent.id,
    )
    context = WorkflowExecutionContext(
        db=db,
        conversation=conversation,
        user_message=message,
        task=task,
        workflow_run=workflow_run,
        prompt="请实现功能",
        channel=f"conversation:{conversation.id}",
        agents=[agent],
    )

    result = asyncio.run(ToolNodeExecutor().execute(node, context))

    assert result.status == "completed"
    assert result.output["result"]["status"] == "completed"
    assert result.output["result"]["output"]["run_id"]


def _memory_session() -> Any:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return session_factory()


def _seed_workspace(db: Any) -> tuple[User, Workspace, Conversation]:
    user = User(
        id="user-external",
        email="external@example.com",
        username="external",
        password_hash="x",
        display_name="External User",
        role="admin",
    )
    workspace = Workspace(id="workspace-external", owner_id=user.id, name="External Workspace")
    conversation = Conversation(
        id="conversation-external",
        creator_id=user.id,
        chat_type="single",
        title="External Agent Chat",
        extra={"workspace_id": workspace.id},
    )
    db.add_all([user, workspace, conversation])
    db.commit()
    return user, workspace, conversation


def _redirect_workspace_var(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import app.services.workspaces.filesystem as filesystem

    root = tmp_path / "var"
    monkeypatch.setattr(filesystem, "backend_var_dir", lambda: root)


def _fake_cli(tmp_path: Path, *, exit_code: int = 0, stderr_text: str = "") -> Path:
    script = tmp_path / f"fake_cli_{exit_code}.py"
    script.write_text(
        "\n".join(
            [
                "from pathlib import Path",
                "import sys",
                f"exit_code = {exit_code}",
                f"stderr_text = {stderr_text!r}",
                "prompt = sys.argv[-1] if len(sys.argv) > 1 else ''",
                "Path('agent_output.txt').write_text('prompt=' + prompt, encoding='utf-8')",
                "print('fake external agent received: ' + prompt, flush=True)",
                "if stderr_text:",
                "    print(stderr_text, file=sys.stderr, flush=True)",
                "raise SystemExit(exit_code)",
            ]
        ),
        encoding="utf-8",
    )
    return script


def _sleeping_cli(tmp_path: Path) -> Path:
    script = tmp_path / "sleeping_cli.py"
    script.write_text(
        "\n".join(
            [
                "import time",
                "print('sleeping external agent', flush=True)",
                "time.sleep(30)",
            ]
        ),
        encoding="utf-8",
    )
    return script
