from __future__ import annotations

from collections.abc import Awaitable, Callable

from sqlalchemy.orm import Session

from app.models import Agent, Conversation, Message, WorkflowRun, utcnow
from app.services.agents.function_types import AgentFunctionLoopResult
from app.services.realtime.event_bus import event_bus
from app.services.serialization import message_to_dict

WorkflowUpdatePublisher = Callable[..., Awaitable[None]]


async def complete_missing_artifact_tool(
    db: Session,
    *,
    conversation: Conversation,
    assistant: Message | None,
    agent: Agent,
    workflow_run: WorkflowRun | None,
    workflow_node_id: str | None,
    channel: str,
    requested_tool: str,
    publish_workflow_update: WorkflowUpdatePublisher,
) -> AgentFunctionLoopResult:
    text = (
        f"当前 Agent（{agent.name}）没有 {requested_tool} 产物工具权限，无法真实生成该产物。"
        "请切换 Writing Agent，或在 Agent 设置里授权对应 artifact.create_* 工具后再试。"
    )
    tool_result = {
        "type": "tool",
        "tool_name": requested_tool,
        "status": "failed",
        "output": text,
    }
    record = {
        "tool_name": requested_tool,
        "tool_call_id": "permission_guard",
        "arguments": {},
        "result": tool_result,
        "status": "failed",
        "round": 0,
    }
    if assistant:
        assistant.content = {"text": text, "thinking": ""}
        assistant.status = "completed"
        db.commit()
        await event_bus.publish(channel, "message:updated", message_to_dict(assistant))
        await event_bus.publish(
            channel,
            "message_stop",
            {
                "agent_message_id": assistant.id,
                "agent_id": agent.id,
                "agent_name": agent.name,
                "stop_reason": "tool_permission_missing",
            },
        )
    await publish_workflow_update(
        db,
        conversation=conversation,
        workflow_run=workflow_run,
        workflow_node_id=workflow_node_id,
        channel=channel,
        status="completed",
        progress=100,
        output={
            "summary": text,
            "tool_results": [record],
            "assistant_message_id": assistant.id if assistant else None,
            "completed_at": utcnow().isoformat(),
        },
        message=text,
    )
    return AgentFunctionLoopResult(
        assistant=assistant,
        text=text,
        thinking="",
        tool_results=[record],
        tool_context={
            "mode": "function_call_loop",
            "agent_id": agent.id,
            "agent_name": agent.name,
            "assistant_message_id": assistant.id if assistant else None,
            "executions": [tool_result],
            "tool_results": [record],
            "summary": text,
        },
    )
