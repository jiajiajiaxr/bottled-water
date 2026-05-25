from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any

from sqlalchemy.orm import Session

from app.models import Agent, Conversation, Message, Task, WorkflowRun
from app.services.workflows.graph import Node


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


REFERENCE_PATTERN = re.compile(r"\{\{\s*(?P<expr>[A-Za-z0-9_.:-]+)\s*\}\}")


def resolve_references(value: Any, outputs: dict[str, dict[str, Any]]) -> Any:
    if isinstance(value, dict):
        return {key: resolve_references(item, outputs) for key, item in value.items()}
    if isinstance(value, list):
        return [resolve_references(item, outputs) for item in value]
    if not isinstance(value, str):
        return value

    def lookup(match: re.Match[str]) -> str:
        expr = match.group("expr")
        node_id, sep, path = expr.partition(".")
        if not sep:
            return ""
        current: Any = outputs.get(node_id, {})
        for part in path.split("."):
            if isinstance(current, dict):
                current = current.get(part)
            else:
                current = None
            if current is None:
                return ""
        return str(current)

    return REFERENCE_PATTERN.sub(lookup, value)
