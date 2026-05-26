from __future__ import annotations

from app.services.workflows.graph import Node
from app.services.workflows.nodes.base import (
    NodeExecutionResult,
    WorkflowExecutionContext,
    WorkflowNodeExecutor,
)


class LoopNodeExecutor(WorkflowNodeExecutor):
    node_type = "loop"

    async def execute(self, node: Node, context: WorkflowExecutionContext) -> NodeExecutionResult:
        node_input = getattr(context, "node_input", {}) or {}
        max_iterations = max(
            1,
            min(
                int(node_input.get("max_iterations") or node.config.get("max_iterations") or 3), 20
            ),
        )
        return NodeExecutionResult(
            output={
                "max_iterations": max_iterations,
                "current_iteration": max_iterations,
                "input": node_input,
            },
            message=f"Loop completed {max_iterations} iterations",
        )
