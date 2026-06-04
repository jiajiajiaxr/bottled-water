from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Agent, Conversation, Message, Subtask, Task, utcnow
from app.services.agents.function_loop import run_agent_function_call_loop
from app.services.agents.tool_loop import run_agentic_tool_loop
from app.services.ark import ark_client
from app.services.chat.artifacts import _publish_tool_artifacts
from app.services.chat.finalizer import finalize_streaming_agent_messages
from app.services.context.builder import ContextBuilder
from app.services.context.state import update_conversation_state_after_turn
from app.services.llm_gateway import stream_model_config_chat
from app.services.output_filter import InternalOutputStreamFilter, strip_internal_agent_output
from app.services.queue import queue_service
from app.services.realtime.event_bus import event_bus
from app.services.serialization import message_to_dict, subtask_to_dict, task_to_dict

logger = logging.getLogger(__name__)


async def _run_direct_agent(
    db: Session,
    *,
    conversation: Conversation,
    user_message: Message,
    agent: Agent,
    prompt: str,
    channel: str,
    runtime_model_config_id: str | None = None,
) -> None:
    """Run a single-chat Agent through the shared Function Call loop."""
    settings = get_settings()
    enable_fc = settings.enable_function_calling
    selected_model_config_id = (
        runtime_model_config_id
        or (user_message.extra or {}).get("model_config_id")
        or (agent.config or {}).get("model_config_id")
    )
    logger.info(
        "[_run_direct_agent] agent=%s enable_fc=%s model_config_id=%s",
        agent.name,
        enable_fc,
        selected_model_config_id,
    )
    if not enable_fc:
        return await _run_direct_agent_without_function_calling(
            db,
            conversation=conversation,
            user_message=user_message,
            agent=agent,
            prompt=prompt,
            channel=channel,
            runtime_model_config_id=str(selected_model_config_id) if selected_model_config_id else None,
        )

    task = Task(
        conversation_id=conversation.id,
        creator_id=conversation.creator_id,
        executor_agent_id=agent.id,
        title=prompt[:80] or f"{agent.name} ????",
        description=prompt,
        status="EXECUTING",
        priority="medium",
        progress=10,
        plan={
            "mode": "direct_worker_function_calling",
            "agent_id": agent.id,
            "agent_name": agent.name,
            "model_config_id": selected_model_config_id,
            "tools": (agent.config or {}).get("tools") or [],
            "skill_ids": (agent.config or {}).get("skill_ids") or [],
            "mcp_server_ids": (agent.config or {}).get("mcp_server_ids") or [],
        },
        input={"prompt": prompt},
        started_at=utcnow(),
    )
    db.add(task)
    db.flush()
    subtask = Subtask(
        parent_task_id=task.id,
        title=f"{agent.name} Function Calling ??",
        description="??????????????Skill ? MCP ???",
        status="EXECUTING",
        order_index=0,
        agent_id=agent.id,
        input={"prompt": prompt},
    )
    db.add(subtask)
    db.commit()
    await queue_service.enqueue(
        {"id": task.id, "conversation_id": conversation.id, "agent_id": agent.id},
        priority=8,
    )
    await event_bus.publish(channel, "task:status_changed", task_to_dict(task))
    await event_bus.publish(channel, "task:subtask_updated", subtask_to_dict(subtask))

    try:
        result = await run_agent_function_call_loop(
            db,
            conversation=conversation,
            user_message=user_message,
            agent=agent,
            prompt=prompt,
            channel=channel,
            mode="direct",
            task=task,
            runtime_model_config_id=str(selected_model_config_id) if selected_model_config_id else None,
            max_tool_rounds=3,
        )
        await _publish_tool_artifacts(db, channel, result.tool_context)
    except Exception as exc:
        logger.exception("direct agent failed: agent=%s", agent.id)
        subtask.status = "FAILED"
        subtask.completed_at = utcnow()
        subtask.output = {"error": str(exc)}
        task.status = "FAILED"
        task.progress = min(max(task.progress or 0, 95), 100)
        task.error_info = {"error": str(exc), "agent_id": agent.id}
        task.completed_at = utcnow()
        conversation.last_message_preview = "本轮响应异常结束，已停止生成。"
        conversation.last_message_sender = agent.name
        conversation.last_message_at = utcnow()
        db.commit()
        await finalize_streaming_agent_messages(
            db,
            conversation=conversation,
            channel=channel,
            status="failed",
            stop_reason="direct_agent_failed",
            fallback_text="本轮响应异常结束，已停止生成。",
        )
        await event_bus.publish(channel, "task:subtask_updated", subtask_to_dict(subtask))
        await event_bus.publish(channel, "task:status_changed", task_to_dict(task))
        await event_bus.publish(
            channel,
            "generation_finished",
            {"conversation_id": conversation.id, "reason": "direct_agent_failed", "status": "failed"},
        )
        return

    failed_result = (
        (result.tool_context or {}).get("status") == "failed"
        or (result.assistant is not None and result.assistant.status in {"failed", "cancelled"})
    )
    subtask.status = "FAILED" if failed_result else "COMPLETED"
    subtask.completed_at = utcnow()
    subtask.output = {"summary": result.text[:500], "tool_results": result.tool_results}
    task.status = "FAILED" if failed_result else "COMPLETED"
    task.progress = 100
    task.output = {
        **(task.output or {}),
        "summary": result.text,
        "tool_results": result.tool_results,
        "agentic_tools": result.tool_context,
    }
    if failed_result:
        task.error_info = {"agent_id": agent.id, "message": result.text[:1000]}
    task.completed_at = utcnow()
    conversation.last_message_preview = result.text[:300]
    conversation.last_message_sender = agent.name
    conversation.last_message_at = utcnow()
    conversation.activity_score = min(100, conversation.activity_score + 6)
    conversation.message_count += 1
    db.commit()
    await event_bus.publish(channel, "task:subtask_updated", subtask_to_dict(subtask))
    await event_bus.publish(channel, "task:status_changed", task_to_dict(task))
    await event_bus.publish(channel, "generation_finished", {"conversation_id": conversation.id, "reason": "direct_agent_completed"})


async def _run_direct_agent_without_function_calling(
    db: Session,
    *,
    conversation: Conversation,
    user_message: Message,
    agent: Agent,
    prompt: str,
    channel: str,
    runtime_model_config_id: str | None = None,
) -> None:
    selected_model_config_id = (
        runtime_model_config_id
        or (user_message.extra or {}).get("model_config_id")
        or (agent.config or {}).get("model_config_id")
    )
    task = Task(
        conversation_id=conversation.id,
        creator_id=conversation.creator_id,
        executor_agent_id=agent.id,
        title=prompt[:80] or f"{agent.name} 单聊任务",
        description=prompt,
        status="EXECUTING",
        priority="medium",
        progress=20,
        plan={
            "mode": "direct_worker_loop",
            "agent_id": agent.id,
            "agent_name": agent.name,
            "model_config_id": selected_model_config_id,
            "tools": (agent.config or {}).get("tools") or [],
            "skill_ids": (agent.config or {}).get("skill_ids") or [],
            "mcp_server_ids": (agent.config or {}).get("mcp_server_ids") or [],
        },
        input={"prompt": prompt},
        started_at=utcnow(),
    )
    db.add(task)
    db.flush()
    subtask = Subtask(
        parent_task_id=task.id,
        title=f"{agent.name} 自主执行",
        description="单聊模式下由当前 Worker 使用自己的模型、工具、Skill 和 MCP 权限执行。",
        status="EXECUTING",
        order_index=0,
        agent_id=agent.id,
        input={"prompt": prompt},
    )
    db.add(subtask)
    db.commit()
    await queue_service.enqueue({"id": task.id, "conversation_id": conversation.id, "agent_id": agent.id}, priority=8)
    await event_bus.publish(channel, "task:status_changed", task_to_dict(task))
    await event_bus.publish(channel, "task:subtask_updated", subtask_to_dict(subtask))

    tool_context = await run_agentic_tool_loop(db, conversation, prompt, max_steps=2, agent=agent)
    await _publish_tool_artifacts(db, channel, tool_context)
    task.output = {**(task.output or {}), "agentic_tools": tool_context}
    task.progress = 70
    db.commit()
    await event_bus.publish(channel, "task:status_changed", task_to_dict(task))

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
        {"agent_message_id": assistant.id, "agent_id": agent.id, "agent_name": agent.name},
    )

    stream_text = ""
    reasoning_text = ""
    system_prompt = (agent.config or {}).get("system_prompt") or agent.description or f"你是 {agent.name}。"
    system_prompt += (
        "\n你正在单聊模式直接响应用户。只使用你被授权的工具/Skill/MCP 结果，"
        "不要伪装成 Master；如果没有工具权限，就作为纯对话 Agent 回复。"
    )
    context_bundle = ContextBuilder(db).build_agent_messages(
        conversation=conversation,
        user_message=user_message,
        agent=agent,
        system_prompt=system_prompt,
        prompt=prompt,
        mode="direct_without_function_calling",
        task=task,
        node_input={"agentic_tool_context": tool_context} if tool_context else None,
    )
    messages = context_bundle.messages
    thinking_enabled = (user_message.extra or {}).get("thinking_enabled") is True
    thinking = {"type": "enabled", "budget_tokens": 1024} if thinking_enabled else None
    model_config_id = selected_model_config_id

    try:
        if model_config_id:
            event_stream = stream_model_config_chat(db, str(model_config_id), messages)
        else:
            event_stream = ark_client.stream_chat(messages, purpose=f"agent:{agent.type}", thinking=thinking)
        stream_filter = InternalOutputStreamFilter()
        reasoning_filter = InternalOutputStreamFilter()
        async for event in event_stream:
            if event.type == "delta":
                if event.text:
                    stream_text += event.text
                    visible_delta = stream_filter.push(event.text)
                    if visible_delta:
                        await event_bus.publish(
                            channel,
                            "content_block_delta",
                            {
                                "agent_message_id": assistant.id,
                                "agent_id": agent.id,
                                "agent_name": agent.name,
                                "delta": {"type": "text_delta", "text": visible_delta},
                            },
                        )
                if event.reasoning:
                    reasoning_text += event.reasoning
                    visible_reasoning = reasoning_filter.push(event.reasoning)
                    if visible_reasoning:
                        await event_bus.publish(
                            channel,
                            "content_block_delta",
                            {
                                "agent_message_id": assistant.id,
                                "agent_id": agent.id,
                                "agent_name": agent.name,
                                "delta": {"type": "reasoning_delta", "text": visible_reasoning},
                            },
                        )
            elif event.type == "error":
                stream_text += f"\n模型调用异常，已降级：{event.error}"
    except Exception as exc:
        stream_text = f"{agent.name} 的专属模型调用失败，已降级：{exc}"
        await event_bus.publish(
            channel,
            "content_block_delta",
            {
                "agent_message_id": assistant.id,
                "agent_id": agent.id,
                "agent_name": agent.name,
                "delta": {"type": "text_delta", "text": stream_text},
            },
        )

    display_text = strip_internal_agent_output(stream_text)
    assistant.content = {
        "text": display_text or f"{agent.name} 已完成本次单聊处理。",
        "thinking": strip_internal_agent_output(reasoning_text) if reasoning_text else "",
    }
    assistant.status = "completed"
    update_conversation_state_after_turn(
        db,
        conversation,
        user_message=user_message,
        assistant_message=assistant,
        final_text=assistant.content["text"],
        tool_results=[],
    )
    subtask.status = "COMPLETED"
    subtask.completed_at = utcnow()
    subtask.output = {"summary": assistant.content["text"][:500], "agentic_tools": tool_context}
    task.status = "COMPLETED"
    task.progress = 100
    task.output = {**(task.output or {}), "summary": assistant.content["text"]}
    task.completed_at = utcnow()
    conversation.last_message_preview = assistant.content["text"][:300]
    conversation.last_message_sender = agent.name
    conversation.last_message_at = utcnow()
    conversation.activity_score = min(100, conversation.activity_score + 6)
    conversation.message_count += 1
    db.commit()
    await event_bus.publish(channel, "message:updated", message_to_dict(assistant))
    await event_bus.publish(channel, "message_stop", {"agent_message_id": assistant.id, "stop_reason": "end_turn"})
    await event_bus.publish(channel, "task:subtask_updated", subtask_to_dict(subtask))
    await event_bus.publish(channel, "task:status_changed", task_to_dict(task))
    await event_bus.publish(channel, "generation_finished", {"conversation_id": conversation.id, "reason": "direct_agent_completed"})
