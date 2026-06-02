from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Conversation, McpToolInvocation, SkillRun, Task, ToolInvocation, WorkflowRun
from app.services.context.compression import compact_json, trim_text


@dataclass
class TaskContext:
    workflow_nodes: dict[str, Any] = field(default_factory=dict)
    tool_invocations: list[dict[str, Any]] = field(default_factory=list)
    skill_runs: list[dict[str, Any]] = field(default_factory=list)
    mcp_invocations: list[dict[str, Any]] = field(default_factory=list)
    task: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "workflow_nodes": self.workflow_nodes,
            "tool_invocations": self.tool_invocations,
            "skill_runs": self.skill_runs,
            "mcp_invocations": self.mcp_invocations,
        }

    def to_text(self) -> str:
        return trim_text(compact_json(self.to_dict(), max_chars=8000), max_chars=8000)


def build_task_context(
    db: Session,
    conversation: Conversation,
    *,
    task: Task | None = None,
    workflow_run: WorkflowRun | None = None,
) -> TaskContext:
    return TaskContext(
        task=_task_payload(task),
        workflow_nodes=_workflow_payload(workflow_run),
        tool_invocations=_tool_invocations(db, conversation),
        skill_runs=_skill_runs(db, conversation),
        mcp_invocations=_mcp_invocations(db, conversation),
    )


def summarize_tool_result(
    db: Session,
    conversation: Conversation,
    result: dict[str, Any],
    *,
    max_chars: int = 4000,
) -> str:
    invocation_id = str(result.get("invocation_id") or "")
    if invocation_id:
        invocation = db.get(ToolInvocation, invocation_id)
        if invocation:
            return compact_json(
                {
                    "tool_name": invocation.tool_name,
                    "status": invocation.status,
                    "result": invocation.result,
                },
                max_chars=max_chars,
            )
        mcp_invocation = db.get(McpToolInvocation, invocation_id)
        if mcp_invocation:
            return compact_json(
                {
                    "tool_name": mcp_invocation.tool_name,
                    "status": mcp_invocation.status,
                    "result": mcp_invocation.result,
                    "error": mcp_invocation.error_message,
                },
                max_chars=max_chars,
            )
    run_id = str(result.get("run_id") or "")
    if run_id:
        skill_run = db.get(SkillRun, run_id)
        if skill_run:
            return compact_json(
                {
                    "skill_id": skill_run.skill_id,
                    "status": skill_run.status,
                    "output": skill_run.output,
                    "error": skill_run.error_message,
                },
                max_chars=max_chars,
            )
    return compact_json(result, max_chars=max_chars)


def _task_payload(task: Task | None) -> dict[str, Any]:
    if not task:
        return {}
    return {
        "id": task.id,
        "title": getattr(task, "title", ""),
        "status": getattr(task, "status", ""),
        "progress": getattr(task, "progress", 0),
        "input": getattr(task, "input", {}),
        "output": getattr(task, "output", {}),
    }


def _workflow_payload(workflow_run: WorkflowRun | None) -> dict[str, Any]:
    if not workflow_run:
        return {}
    return {
        "id": workflow_run.id,
        "status": getattr(workflow_run, "status", ""),
        "progress": getattr(workflow_run, "progress", 0),
        "node_states": getattr(workflow_run, "node_states", {}) or {},
        "edge_states": getattr(workflow_run, "edge_states", {}) or {},
    }


def _tool_invocations(db: Session, conversation: Conversation) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(ToolInvocation)
        .where(ToolInvocation.conversation_id == conversation.id)
        .order_by(ToolInvocation.created_at.desc())
        .limit(8)
    ).all()
    return [
        {
            "id": item.id,
            "tool_name": item.tool_name,
            "status": item.status,
            "result": _compact_result(item.result),
        }
        for item in rows
    ]


def _skill_runs(db: Session, conversation: Conversation) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(SkillRun)
        .where(SkillRun.conversation_id == conversation.id)
        .order_by(SkillRun.created_at.desc())
        .limit(8)
    ).all()
    return [
        {
            "id": item.id,
            "skill_id": item.skill_id,
            "status": item.status,
            "output": _compact_result(item.output),
        }
        for item in rows
    ]


def _mcp_invocations(db: Session, conversation: Conversation) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(McpToolInvocation)
        .where(McpToolInvocation.conversation_id == conversation.id)
        .order_by(McpToolInvocation.created_at.desc())
        .limit(8)
    ).all()
    return [
        {
            "id": item.id,
            "server_id": item.server_id,
            "tool_name": item.tool_name,
            "status": item.status,
            "result": _compact_result(item.result),
            "error": item.error_message,
        }
        for item in rows
    ]


def _compact_result(value: dict[str, Any] | None) -> dict[str, Any] | str:
    if not value:
        return {}
    text = compact_json(value, max_chars=1200)
    return value if len(text) < 1200 else text
