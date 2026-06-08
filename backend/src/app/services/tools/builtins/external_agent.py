from __future__ import annotations

from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.core.errors import ValidationAppError
from app.models import ExternalAgentRun, User
from app.services.external_agents.adapters._cli import get_run_for_user
from app.services.external_agents.base import ExternalAgentRunRequest
from app.services.external_agents.registry import (
    get_external_agent_adapter,
    list_external_agent_adapters,
)
from app.services.external_agents.workspace import external_agent_cwd


def invoke_external_agent_tool(
    db: Session,
    user: User,
    name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    if name == "external_agent.invoke":
        return _invoke(db, user, arguments)
    if name == "external_agent.probe":
        return _probe(arguments)
    if name == "external_agent.run_codex":
        return _run(db, user, "codex", arguments)
    if name == "external_agent.run_claude_code":
        return _run(db, user, "claude_code", arguments)
    if name == "external_agent.cancel":
        return _cancel(db, user, arguments)
    if name == "external_agent.status":
        return _status(db, user, arguments)
    raise ValidationAppError("未知外部 Agent 工具")


def _invoke(db: Session, user: User, arguments: dict[str, Any]) -> dict[str, Any]:
    normalized = _normalize_invoke_arguments(arguments)
    action = _action(normalized)
    if action == "probe":
        return _probe(normalized)
    if action == "run":
        return _run(db, user, _provider(normalized), normalized)
    if action == "cancel":
        return _cancel(db, user, normalized)
    if action == "status":
        return _status(db, user, normalized)
    raise ValidationAppError("external_agent.invoke action must be run, probe, cancel, or status")


def list_recent_external_agent_runs(
    db: Session,
    user: User,
    *,
    workspace_id: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    query = select(ExternalAgentRun).where(ExternalAgentRun.deleted_at.is_(None))
    if user.role != "admin":
        query = query.where(ExternalAgentRun.owner_id == user.id)
    if workspace_id:
        query = query.where(ExternalAgentRun.workspace_id == workspace_id)
    rows = db.scalars(query.order_by(desc(ExternalAgentRun.created_at)).limit(limit)).all()
    return [_run_payload(row) for row in rows]


def _probe(arguments: dict[str, Any]) -> dict[str, Any]:
    provider = str(arguments.get("provider") or "").strip()
    adapters = [get_external_agent_adapter(provider)] if provider else list_external_agent_adapters()
    probes = [adapter.probe().to_dict() for adapter in adapters]
    return {
        "status": "succeeded",
        "providers": probes,
        "degraded": [item for item in probes if not item.get("installed")],
    }


def _run(db: Session, user: User, provider: str, arguments: dict[str, Any]) -> dict[str, Any]:
    prompt = str(arguments.get("prompt") or arguments.get("task") or "").strip()
    if not prompt:
        raise ValidationAppError("prompt 不能为空")
    workspace_id, cwd = external_agent_cwd(db, arguments, provider=provider)
    adapter = get_external_agent_adapter(provider)
    request = ExternalAgentRunRequest(
        provider=provider,
        prompt=prompt,
        workspace_id=workspace_id,
        conversation_id=str(arguments.get("conversation_id") or "") or None,
        agent_id=str(arguments.get("agent_id") or "") or None,
        cwd=cwd,
        timeout_ms=_timeout_ms(arguments),
        wait=bool(arguments.get("wait", True)),
        metadata={"source": "tool", "tool": "external_agent.invoke", "provider": provider},
    )
    return adapter.start_run(db, user=user, request=request)


def _cancel(db: Session, user: User, arguments: dict[str, Any]) -> dict[str, Any]:
    run = get_run_for_user(db, user, str(arguments.get("run_id") or ""))
    adapter = get_external_agent_adapter(run.provider)
    return adapter.cancel_run(db, user=user, run=run)


def _status(db: Session, user: User, arguments: dict[str, Any]) -> dict[str, Any]:
    run = get_run_for_user(db, user, str(arguments.get("run_id") or ""))
    adapter = get_external_agent_adapter(run.provider)
    return adapter.run_payload(run)


def _normalize_invoke_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    legacy_tool = str(arguments.get("_legacy_tool_name") or "")
    if legacy_tool == "external_agent.probe":
        return {**arguments, "action": arguments.get("action") or "probe"}
    if legacy_tool == "external_agent.run_codex":
        return {
            **arguments,
            "action": arguments.get("action") or "run",
            "provider": arguments.get("provider") or "codex",
        }
    if legacy_tool == "external_agent.run_claude_code":
        return {
            **arguments,
            "action": arguments.get("action") or "run",
            "provider": arguments.get("provider") or "claude_code",
        }
    if legacy_tool == "external_agent.cancel":
        return {**arguments, "action": arguments.get("action") or "cancel"}
    if legacy_tool == "external_agent.status":
        return {**arguments, "action": arguments.get("action") or "status"}
    return arguments


def _action(arguments: dict[str, Any]) -> str:
    value = str(arguments.get("action") or "").strip().lower().replace("-", "_")
    aliases = {
        "start": "run",
        "invoke": "run",
        "call": "run",
        "detect": "probe",
        "list": "probe",
        "stop": "cancel",
        "query": "status",
        "get": "status",
    }
    value = aliases.get(value, value)
    if value:
        return value
    if arguments.get("run_id"):
        return "status"
    if arguments.get("prompt") or arguments.get("task"):
        return "run"
    return "probe"


def _provider(arguments: dict[str, Any]) -> str:
    value = str(arguments.get("provider") or arguments.get("agent") or "codex").strip().lower().replace("-", "_")
    aliases = {
        "claude": "claude_code",
        "claudecode": "claude_code",
        "claude_code_cli": "claude_code",
        "open_code": "opencode",
        "open_code_cli": "opencode",
        "opencode_cli": "opencode",
    }
    return aliases.get(value, value)


def _timeout_ms(arguments: dict[str, Any]) -> int:
    value = int(arguments.get("timeout_ms") or arguments.get("timeout") or 120_000)
    return max(1_000, min(value, 600_000))


def _run_payload(run: ExternalAgentRun) -> dict[str, Any]:
    return {
        "status": run.status,
        "provider": run.provider,
        "run_id": run.id,
        "workspace_id": run.workspace_id,
        "conversation_id": run.conversation_id,
        "agent_id": run.agent_id,
        "cwd": run.cwd,
        "changed_files": run.changed_files or [],
        "stdout_tail": run.stdout_tail,
        "stderr_tail": run.stderr_tail,
        "exit_code": run.exit_code,
        "duration_ms": run.duration_ms,
        "error": run.error,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
    }
