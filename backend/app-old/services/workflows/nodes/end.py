from __future__ import annotations

from app.services.workflows.nodes.base import (
    NodeExecutionResult,
    WorkflowExecutionContext,
    WorkflowNodeExecutor,
)
from app.services.workflows.graph import Node


class EndNodeExecutor(WorkflowNodeExecutor):
    node_type = "end"

    async def execute(self, node: Node, context: WorkflowExecutionContext) -> NodeExecutionResult:
        summaries = []
        node_input = getattr(context, "node_input", {}) or {}
        upstream = node_input.get("upstream") or context.outputs
        for node_id, output in upstream.items():
            text = output.get("text") or output.get("summary") or output.get("result")
            if text:
                summaries.append(f"{node_id}: {str(text)[:500]}")
        return NodeExecutionResult(
            output={"outputs": upstream, "summary": "\n".join(summaries)},
            message="Workflow completed",
        )
