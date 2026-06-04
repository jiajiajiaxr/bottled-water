from __future__ import annotations

from app.models import Agent, User
from app.services.agents.tool_loop import execute_tool_by_name
from app.services.workflows.events import publish_tool_event
from app.services.workflows.graph import Node
from app.services.workflows.io import input_mapping_as_arguments, resolve_value
from app.services.workflows.nodes.base import (
    NodeExecutionResult,
    WorkflowExecutionContext,
    WorkflowNodeExecutor,
)


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
            agent = next(
                (
                    item
                    for item in context.agents
                    if tool_name in ((item.config or {}).get("tools") or [])
                ),
                None,
            )
        if agent is None:
            agent = Agent(
                id="workflow-tool-node",
                name="Workflow Tool Node",
                type="tool",
                config={"tools": [tool_name]},
            )
        user = context.db.get(User, context.conversation.creator_id)
        node_input = getattr(context, "node_input", {}) or {}
        arguments = input_mapping_as_arguments(node_input)
        legacy_arguments = node.config.get("arguments")
        if isinstance(legacy_arguments, dict):
            scope = {
                "input": context.prompt,
                "nodes": context.outputs,
                "upstream": {
                    "nodes": node_input.get("upstream", {}),
                    "text": node_input.get("upstream_text", ""),
                },
            }
            arguments.update(resolve_value(legacy_arguments, scope))
        arguments.setdefault("prompt", context.prompt)
        await publish_tool_event(
            context.channel,
            context.workflow_run,
            node.id,
            "workflow:tool_call_started",
            {"tool_name": tool_name, "arguments": arguments},
        )
        result = await execute_tool_by_name(
            context.db,
            agent=agent,
            user=user,
            conversation=context.conversation,
            tool_name=tool_name,
            arguments=arguments,
        )
        status = str(result.get("status") or result.get("result", {}).get("status") or "succeeded")
        node_status = "failed" if status.startswith("failed") or status == "error" else "completed"
        await publish_tool_event(
            context.channel,
            context.workflow_run,
            node.id,
            "workflow:tool_call_completed",
            {"tool_name": tool_name, "status": status},
        )
        return NodeExecutionResult(
            status=node_status,
            output={
                "tool_name": tool_name,
                "arguments": arguments,
                "result": result,
                **(
                    {"error": str(result.get("output") or result)}
                    if node_status == "failed"
                    else {}
                ),
            },
            message=f"Tool {tool_name} {status}",
        )
