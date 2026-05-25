from __future__ import annotations

from app.models import Agent, User
from app.services.agents.tool_loop import execute_tool_by_name
from app.services.workflows.graph import Node
from app.services.workflows.nodes.base import NodeExecutionResult, WorkflowExecutionContext, WorkflowNodeExecutor, resolve_references


class ToolNodeExecutor(WorkflowNodeExecutor):
    node_type = "tool"

    async def execute(self, node: Node, context: WorkflowExecutionContext) -> NodeExecutionResult:
        tool_name = str(node.config.get("tool_name") or "")
        if not tool_name:
            return NodeExecutionResult(status="skipped", output={"reason": "missing tool_name"})
        agent = None
        agent_id = node.agent_id or node.config.get("agent_id")
        if agent_id:
            agent = context.db.get(Agent, str(agent_id))
        if agent is None:
            agent = next((item for item in context.agents if tool_name in ((item.config or {}).get("tools") or [])), None)
        if agent is None:
            agent = Agent(id="workflow-tool-node", name="Workflow Tool Node", type="tool", config={"tools": [tool_name]})
        user = context.db.get(User, context.conversation.creator_id)
        arguments = dict(node.config.get("arguments") if isinstance(node.config.get("arguments"), dict) else {})
        arguments = resolve_references(arguments, context.outputs)
        arguments.setdefault("prompt", context.prompt)
        result = await execute_tool_by_name(
            context.db,
            agent=agent,
            user=user,
            conversation=context.conversation,
            tool_name=tool_name,
            arguments=arguments,
        )
        return NodeExecutionResult(output={"tool_name": tool_name, "result": result}, message=f"Tool {tool_name} completed")
