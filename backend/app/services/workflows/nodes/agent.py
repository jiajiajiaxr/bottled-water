from __future__ import annotations

from app.models import Agent
from app.services.agents.function_loop import run_agent_function_call_loop
from app.services.workflows.graph import Node
from app.services.workflows.nodes.base import NodeExecutionResult, WorkflowExecutionContext, WorkflowNodeExecutor


class AgentNodeExecutor(WorkflowNodeExecutor):
    node_type = "agent"

    async def execute(self, node: Node, context: WorkflowExecutionContext) -> NodeExecutionResult:
        agent_id = node.agent_id or node.config.get("agent_id")
        agent = context.db.get(Agent, str(agent_id)) if agent_id else None
        if agent is None:
            agent = next((item for item in context.agents if item.id == agent_id), None)
        if not agent or agent.deleted_at is not None:
            return NodeExecutionResult(
                status="failed",
                output={"error": "agent not found", "agent_id": agent_id},
                message="Agent not found",
            )
        result = await run_agent_function_call_loop(
            context.db,
            conversation=context.conversation,
            user_message=context.user_message,
            agent=agent,
            prompt=f"{context.prompt}\n\nWorkflow node: {node.title}\n{node.meta}",
            channel=context.channel,
            mode="workflow-agent-node",
            task=context.task,
            workflow_run=context.workflow_run,
            workflow_node_id=node.id,
            node_title=node.title,
            max_tool_rounds=int(node.config.get("max_tool_rounds") or 3),
        )
        return NodeExecutionResult(
            output={
                **result.tool_context,
                "text": result.text,
                "assistant_message_id": result.assistant.id,
            },
            message=f"{agent.name} completed",
        )


class ReviewNodeExecutor(AgentNodeExecutor):
    node_type = "review"
