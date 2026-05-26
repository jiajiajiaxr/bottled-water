from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.models import Agent, Conversation, Message, Task, WorkflowRun
from app.services.workflows.graph import Node
from app.services.workflows.io import resolve_references as _resolve_references


@dataclass
class WorkflowExecutionContext:
    db: Session
    conversation: Conversation
    user_message: Message
    task: Task
    workflow_run: WorkflowRun
    prompt: str
    channel: str
    agents: list[Agent]
    output_mode: str = "independent_messages"
    outputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    node_input: dict[str, Any] = field(default_factory=dict)
    cancelled: bool = False


@dataclass
class NodeExecutionResult:
    status: str = "completed"
    output: dict[str, Any] = field(default_factory=dict)
    branch: str | None = None
    message: str | None = None
    retries: int = 0


class WorkflowNodeExecutor:
    node_type = "base"

    async def execute(self, node: Node, context: WorkflowExecutionContext) -> NodeExecutionResult:
        return NodeExecutionResult(output={"node_id": node.id, "type": node.type})


def resolve_references(value: Any, outputs: dict[str, dict[str, Any]]) -> Any:
    """兼容旧模块导入的模板解析入口。"""
    return _resolve_references(value, outputs)
