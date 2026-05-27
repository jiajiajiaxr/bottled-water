from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Agent, Conversation, Message, Task, User, WorkflowRun, utcnow
from app.services.agents.function_messages import agent_system_prompt, tool_arguments, tool_names
from app.services.agents.function_types import AgentFunctionLoopResult
from app.services.agents.permission_guard import complete_missing_artifact_tool
from app.services.agents.tool_loop import build_tools_for_agent, execute_tool_by_name
from app.services.ark import ark_client
from app.services.llm.tool_calls import detect_artifact_tool
from app.services.llm_gateway import stream_model_config_chat
from app.services.output_filter import strip_internal_agent_output
from app.services.realtime.event_bus import event_bus
from app.services.serialization import message_to_dict, task_to_dict
from app.services.skills.context import activated_skill_context
from app.services.workflows.runtime import _set_workflow_node_state, mutate_workflow_run_locked

logger = logging.getLogger(__name__)


async def _publish_workflow_update(
    db: Session,
    *,
    conversation: Conversation,
    workflow_run: WorkflowRun | None,
    workflow_node_id: str | None,
    channel: str,
    status: str,
    progress: int,
    output: dict[str, Any] | None = None,
    message: str | None = None,
) -> None:
    if not workflow_run or not workflow_node_id:
        return

    def _mutate(run: WorkflowRun) -> None:
        _set_workflow_node_state(
            run,
            workflow_node_id,
            status=status,
            progress=progress,
            output=output,
            message=message,
        )

    await mutate_workflow_run_locked(db, conversation, workflow_run, _mutate)
    await event_bus.publish(
        channel,
        "workflow:run_updated",
        {
            "run_id": workflow_run.id,
            "status": workflow_run.status,
            "progress": workflow_run.progress,
            "node_id": workflow_node_id,
        },
    )


async def _publish_text_delta(
    *,
    channel: str,
    assistant: Message | None,
    agent: Agent,
    text: str,
    delta_type: str = "text_delta",
    emit_message: bool,
) -> None:
    if not emit_message or not assistant or not text:
        return
    await event_bus.publish(
        channel,
        "content_block_delta",
        {
            "agent_message_id": assistant.id,
            "agent_id": agent.id,
            "agent_name": agent.name,
            "delta": {"type": delta_type, "text": text},
        },
    )


async def _publish_message_tool_event(
    *,
    channel: str,
    assistant: Message | None,
    agent: Agent,
    event_name: str,
    tool_name: str,
    tool_call_id: str,
    emit_message: bool,
    status: str | None = None,
) -> None:
    if not emit_message or not assistant:
        return
    await event_bus.publish(
        channel,
        event_name,
        {
            "agent_message_id": assistant.id,
            "agent_id": agent.id,
            "agent_name": agent.name,
            "tool_name": tool_name,
            "tool_call_id": tool_call_id,
            **({"status": status} if status else {}),
        },
    )


async def run_agent_function_call_loop(
    db: Session,
    *,
    conversation: Conversation,
    user_message: Message,
    agent: Agent,
    prompt: str,
    channel: str,
    mode: str,
    task: Task | None = None,
    workflow_run: WorkflowRun | None = None,
    workflow_node_id: str | None = None,
    node_title: str | None = None,
    max_tool_rounds: int = 3,
    emit_message: bool = True,
) -> AgentFunctionLoopResult:
    """Run one Agent as an independent OpenAI-style function-call loop."""
    settings = get_settings()
    user = db.get(User, conversation.creator_id)
    tools = build_tools_for_agent(db, agent) if settings.enable_function_calling else []
    allowed_tool_names = tool_names(tools)
    model_config_id = (agent.config or {}).get("model_config_id")
    logger.info(
        "[agent_function_loop] start agent=%s/%s mode=%s model_config_id=%s exposed_tools=%s",
        agent.name,
        agent.id,
        mode,
        model_config_id,
        sorted(allowed_tool_names),
    )

    assistant: Message | None = None
    if emit_message:
        assistant = Message(
            conversation_id=conversation.id,
            sender_type="agent",
            sender_id=agent.id,
            sender_name=agent.name,
            content_type="text",
            content={"text": ""},
            status="streaming",
        )
        db.add(assistant)
        db.commit()
        db.refresh(assistant)
        await event_bus.publish(
            channel,
            "message_start",
            {
                "agent_message_id": assistant.id,
                "agent_id": agent.id,
                "agent_name": agent.name,
            },
        )

    await _publish_workflow_update(
        db,
        conversation=conversation,
        workflow_run=workflow_run,
        workflow_node_id=workflow_node_id,
        channel=channel,
        status="running",
        progress=20,
        output={
            "agent_id": agent.id,
            "agent_name": agent.name,
            "assistant_message_id": assistant.id if assistant else None,
            "model_config_id": model_config_id,
            "tool_count": len(tools),
            "tool_names": sorted(allowed_tool_names),
        },
        message=f"{agent.name} 正在组织回复",
    )

    requested_artifact_tool = detect_artifact_tool(prompt)
    if requested_artifact_tool and requested_artifact_tool not in allowed_tool_names:
        logger.info(
            "[agent_function_loop] missing_artifact_tool agent=%s requested=%s exposed_tools=%s",
            agent.id,
            requested_artifact_tool,
            sorted(allowed_tool_names),
        )
        return await complete_missing_artifact_tool(
            db,
            conversation=conversation,
            assistant=assistant,
            agent=agent,
            workflow_run=workflow_run,
            workflow_node_id=workflow_node_id,
            channel=channel,
            requested_tool=requested_artifact_tool,
            publish_workflow_update=_publish_workflow_update,
        )

    skill_context = activated_skill_context(db, agent)
    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": agent_system_prompt(
                agent,
                mode=mode,
                node_title=node_title,
                skill_context=skill_context,
            ),
        },
        {"role": "user", "content": prompt},
    ]
    stream_text = ""
    reasoning_text = ""
    tool_results: list[dict[str, Any]] = []
    thinking_enabled = (user_message.extra or {}).get("thinking_enabled") is True
    thinking = {"type": "enabled", "budget_tokens": 1024} if thinking_enabled else None

    for round_num in range(max_tool_rounds + 1):
        current_text = ""
        current_tool_calls: list[dict[str, Any]] | None = None
        try:
            if model_config_id:
                event_stream = stream_model_config_chat(
                    db,
                    str(model_config_id),
                    messages,
                    tools=tools if tools else None,
                )
            else:
                event_stream = ark_client.stream_chat(
                    messages,
                    purpose=f"agent:{agent.type}",
                    tools=tools if tools else None,
                    thinking=thinking,
                )
            async for event in event_stream:
                if event.type == "delta":
                    if event.text:
                        stream_text += event.text
                        current_text += event.text
                        await _publish_text_delta(
                            channel=channel,
                            assistant=assistant,
                            agent=agent,
                            text=event.text,
                            emit_message=emit_message,
                        )
                    if event.reasoning:
                        reasoning_text += event.reasoning
                        await _publish_text_delta(
                            channel=channel,
                            assistant=assistant,
                            agent=agent,
                            text=event.reasoning,
                            delta_type="reasoning_delta",
                            emit_message=emit_message,
                        )
                elif event.type == "tool_calls":
                    current_tool_calls = event.tool_calls or []
                    logger.info(
                        "[agent_function_loop] tool_calls_received agent=%s round=%s calls=%s",
                        agent.id,
                        round_num,
                        [
                            (item.get("function") or {}).get("name")
                            for item in current_tool_calls
                            if isinstance(item, dict)
                        ],
                    )
                elif event.type == "usage" and emit_message and assistant:
                    await event_bus.publish(
                        channel,
                        "usage",
                        {"agent_message_id": assistant.id, "agent_id": agent.id, "usage": event.usage},
                    )
                elif event.type == "error":
                    text = f"\n模型调用异常，已降级：{event.error}"
                    stream_text += text
                    await _publish_text_delta(
                        channel=channel,
                        assistant=assistant,
                        agent=agent,
                        text=text,
                        emit_message=emit_message,
                    )
        except Exception as exc:
            logger.exception("agent function loop stream failed: agent=%s", agent.id)
            if not stream_text:
                stream_text = f"模型调用异常，已降级：{exc}"
                await _publish_text_delta(
                    channel=channel,
                    assistant=assistant,
                    agent=agent,
                    text=stream_text,
                    emit_message=emit_message,
                )
            break

        if not current_tool_calls or round_num >= max_tool_rounds:
            if round_num == 0 and not current_tool_calls:
                logger.info(
                    "[agent_function_loop] no_tool_calls agent=%s model_config_id=%s requested_artifact_tool=%s exposed_tools=%s",
                    agent.id,
                    model_config_id,
                    requested_artifact_tool,
                    sorted(allowed_tool_names),
                )
            break

        round_tool_results: list[dict[str, Any]] = []
        for tool_call in current_tool_calls:
            function = tool_call.get("function") if isinstance(tool_call, dict) else {}
            function = function if isinstance(function, dict) else {}
            tool_name = str(function.get("name") or "")
            tool_call_id = str(tool_call.get("id") or f"call_{round_num}_{len(tool_results) + 1}")
            arguments = tool_arguments(str(function.get("arguments") or ""))
            logger.info(
                "[agent_function_loop] tool_call agent=%s name=%s arguments=%s",
                agent.id,
                tool_name,
                json.dumps(arguments, ensure_ascii=False, default=str)[:1200],
            )
            await _publish_message_tool_event(
                channel=channel,
                assistant=assistant,
                agent=agent,
                event_name="tool_call_start",
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                emit_message=emit_message,
            )
            await _publish_workflow_update(
                db,
                conversation=conversation,
                workflow_run=workflow_run,
                workflow_node_id=workflow_node_id,
                channel=channel,
                status="running",
                progress=min(85, 35 + round_num * 15),
                output={
                    "active_tool": tool_name,
                    "tool_calls": [
                        *[
                            {
                                "tool_name": item.get("tool_name"),
                                "tool_call_id": item.get("tool_call_id"),
                                "status": item.get("status"),
                            }
                            for item in tool_results
                        ],
                        {"tool_name": tool_name, "tool_call_id": tool_call_id, "status": "running"},
                    ],
                },
                message=f"{agent.name} 正在调用 {tool_name}",
            )

            if tool_name not in allowed_tool_names:
                result = {
                    "type": "tool",
                    "tool_name": tool_name,
                    "status": "failed",
                    "output": "Agent 未被授权调用该工具",
                }
            else:
                result = await execute_tool_by_name(
                    db,
                    agent=agent,
                    user=user,
                    conversation=conversation,
                    tool_name=tool_name,
                    arguments=arguments,
                )
            status = str(result.get("status") or "unknown")
            logger.info(
                "[agent_function_loop] tool_result agent=%s name=%s status=%s invocation_id=%s",
                agent.id,
                tool_name,
                status,
                result.get("invocation_id"),
            )
            record = {
                "tool_name": tool_name,
                "tool_call_id": tool_call_id,
                "arguments": arguments,
                "result": result,
                "status": status,
                "round": round_num,
            }
            tool_results.append(record)
            round_tool_results.append(record)
            db.commit()
            await _publish_message_tool_event(
                channel=channel,
                assistant=assistant,
                agent=agent,
                event_name="tool_call_done",
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                emit_message=emit_message,
                status=status,
            )
            await _publish_workflow_update(
                db,
                conversation=conversation,
                workflow_run=workflow_run,
                workflow_node_id=workflow_node_id,
                channel=channel,
                status="running",
                progress=min(90, 45 + round_num * 15),
                output={
                    "tool_results": [
                        {
                            "tool_name": item.get("tool_name"),
                            "tool_call_id": item.get("tool_call_id"),
                            "status": item.get("status"),
                            "result": item.get("result"),
                        }
                        for item in tool_results
                    ]
                },
                message=f"{agent.name} 已完成 {tool_name}",
            )

        messages.append({"role": "assistant", "content": current_text or "", "tool_calls": current_tool_calls})
        for item in round_tool_results:
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": item["tool_call_id"],
                    "content": json.dumps(item["result"], ensure_ascii=False)[:4000],
                }
            )
        if task:
            task.progress = max(task.progress or 0, min(90, 25 + (round_num + 1) * 15))
            db.commit()
            await event_bus.publish(channel, "task:status_changed", task_to_dict(task))

    final_text = strip_internal_agent_output(stream_text) or f"{agent.name} 已完成本次处理。"
    thinking_text = strip_internal_agent_output(reasoning_text) if reasoning_text else ""
    assistant_message_id = assistant.id if assistant else None
    if assistant:
        assistant.content = {"text": final_text, "thinking": thinking_text}
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
                "stop_reason": "end_turn",
            },
        )

    await _publish_workflow_update(
        db,
        conversation=conversation,
        workflow_run=workflow_run,
        workflow_node_id=workflow_node_id,
        channel=channel,
        status="completed",
        progress=100,
        output={
            "summary": final_text[:1000],
            "tool_results": tool_results,
            "assistant_message_id": assistant_message_id,
            "completed_at": utcnow().isoformat(),
        },
        message=f"{agent.name} 已完成回复",
    )
    return AgentFunctionLoopResult(
        assistant=assistant,
        text=final_text,
        thinking=thinking_text,
        tool_results=tool_results,
        tool_context={
            "mode": "function_call_loop",
            "agent_id": agent.id,
            "agent_name": agent.name,
            "assistant_message_id": assistant_message_id,
            "model_config_id": model_config_id,
            "executions": [item["result"] for item in tool_results],
            "tool_results": tool_results,
            "summary": "\n".join(
                f"- {item.get('tool_name')}: {item.get('status')}" for item in tool_results
            ),
        },
    )
