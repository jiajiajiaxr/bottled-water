from __future__ import annotations

from app.services.workflows.nodes.base import NodeExecutionResult, WorkflowExecutionContext, WorkflowNodeExecutor
from app.services.workflows.graph import Node


class EndNodeExecutor(WorkflowNodeExecutor):
    node_type = "end"

    async def execute(self, node: Node, context: WorkflowExecutionContext) -> NodeExecutionResult:
        summaries = []
        for node_id, output in context.outputs.items():
            text = output.get("text") or output.get("summary") or output.get("result")
            if text:
                summaries.append(f"{node_id}: {str(text)[:500]}")
        return NodeExecutionResult(
            output={"outputs": context.outputs, "summary": "\n".join(summaries)},
            message="Workflow completed",
        )
