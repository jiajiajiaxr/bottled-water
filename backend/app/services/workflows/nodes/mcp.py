from __future__ import annotations

from app.models import McpServer, User
from app.services.agents.tool_loop import execute_mcp_action
from app.services.workflows.events import publish_tool_event
from app.services.workflows.graph import Node
from app.services.workflows.nodes.base import NodeExecutionResult, WorkflowExecutionContext, WorkflowNodeExecutor, resolve_references


class McpNodeExecutor(WorkflowNodeExecutor):
    node_type = "mcp"

    async def execute(self, node: Node, context: WorkflowExecutionContext) -> NodeExecutionResult:
        server_id = str(node.config.get("server_id") or "")
        tool_name = str(node.config.get("tool_name") or "")
        server = context.db.get(McpServer, server_id) if server_id else None
        if not server or not tool_name:
            return NodeExecutionResult(status="failed", output={"error": "mcp server or tool missing", "server_id": server_id, "tool_name": tool_name})
        user = context.db.get(User, context.conversation.creator_id)
        prompt = str(resolve_references(node.config.get("prompt") or context.prompt, context.outputs))
        await publish_tool_event(
            context.channel,
            context.workflow_run,
            node.id,
            "workflow:tool_call_started",
            {"type": "mcp", "server_id": server_id, "tool_name": tool_name},
        )
        result = await execute_mcp_action(
            context.db,
            server=server,
            name=tool_name,
            user=user,
            conversation=context.conversation,
            prompt=prompt,
        )
        status = str(result.get("status") or "succeeded")
        node_status = "failed" if status.startswith("failed") or status == "error" else "completed"
        await publish_tool_event(
            context.channel,
            context.workflow_run,
            node.id,
            "workflow:tool_call_completed",
            {"type": "mcp", "server_id": server_id, "tool_name": tool_name, "status": status},
        )
        return NodeExecutionResult(
            status=node_status,
            output={
                "server_id": server_id,
                "tool_name": tool_name,
                "prompt": prompt,
                "result": result,
                **({"error": str(result.get("output") or result)} if node_status == "failed" else {}),
            },
        )
