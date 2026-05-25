from __future__ import annotations

import re

from app.services.workflows.graph import Node
from app.services.workflows.nodes.base import NodeExecutionResult, WorkflowExecutionContext, WorkflowNodeExecutor


class ConditionNodeExecutor(WorkflowNodeExecutor):
    node_type = "condition"

    async def execute(self, node: Node, context: WorkflowExecutionContext) -> NodeExecutionResult:
        expression = str(node.config.get("expression") or "true").strip()
        branches = node.config.get("branches") if isinstance(node.config.get("branches"), list) else ["true", "false"]
        matched = str(branches[0] if branches else "true")
        if expression.lower() in {"false", "no", "0"}:
            matched = str(branches[1] if len(branches) > 1 else "false")
        elif expression.lower() not in {"true", "yes", "1"}:
            match = re.search(r"contains\\((?P<value>.+)\\)", expression)
            if match:
                needle = match.group("value").strip("'\" ")
                matched = str(branches[0] if needle in context.prompt else (branches[1] if len(branches) > 1 else "false"))
        return NodeExecutionResult(
            output={"expression": expression, "matched_branch": matched},
            branch=matched,
            message=f"Condition matched {matched}",
        )
