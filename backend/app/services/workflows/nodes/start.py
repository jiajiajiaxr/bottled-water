from __future__ import annotations

from app.services.workflows.nodes.base import NodeExecutionResult, WorkflowExecutionContext, WorkflowNodeExecutor
from app.services.workflows.graph import Node


class StartNodeExecutor(WorkflowNodeExecutor):
    node_type = "start"

    async def execute(self, node: Node, context: WorkflowExecutionContext) -> NodeExecutionResult:
        return NodeExecutionResult(output={"input": context.prompt}, message="Workflow started")
