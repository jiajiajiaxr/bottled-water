from __future__ import annotations

from app.models import McpServer, User
from app.services.agents.tool_loop import execute_mcp_action
from app.services.workflows.graph import Node
from app.services.workflows.nodes.base import NodeExecutionResult, WorkflowExecutionContext, WorkflowNodeExecutor, resolve_references


class McpNodeExecutor(WorkflowNodeExecutor):
    node_type = "mcp"

    async def execute(self, node: Node, context: WorkflowExecutionContext) -> NodeExecutionResult:
        server_id = str(node.config.get("server_id") or "")
        tool_name = str(node.config.get("tool_name") or "")
        server = context.db.get(McpServer, server_id) if server_id else None
        if not server or not tool_name:
            return NodeExecutionResult(status="skipped", output={"reason": "mcp server or tool missing"})
        user = context.db.get(User, context.conversation.creator_id)
        result = await execute_mcp_action(
            context.db,
            server=server,
            name=tool_name,
            user=user,
            conversation=context.conversation,
            prompt=str(resolve_references(node.config.get("prompt") or context.prompt, context.outputs)),
        )
        return NodeExecutionResult(output={"server_id": server_id, "tool_name": tool_name, "result": result})
