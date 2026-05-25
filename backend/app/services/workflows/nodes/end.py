from __future__ import annotations

from app.services.workflows.nodes.base import NodeExecutionResult, WorkflowExecutionContext, WorkflowNodeExecutor
from app.services.workflows.graph import Node


class EndNodeExecutor(WorkflowNodeExecutor):
    node_type = "end"

    async def execute(self, node: Node, context: WorkflowExecutionContext) -> NodeExecutionResult:
        return NodeExecutionResult(output={"outputs": context.outputs}, message="Workflow completed")
