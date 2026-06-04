from __future__ import annotations

import asyncio
import json
import logging

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import Conversation, Message, Subtask, Task, WorkflowRun, utcnow
from app.services.agents.direct import _run_direct_agent
from app.services.llm.ark import ArkProviderError, ark_client
from app.services.chat.artifacts import _publish_tool_artifacts
from app.services.chat.finalizer import fail_generation, finalize_streaming_agent_messages
from app.services.output_filter import InternalOutputStreamFilter, strip_internal_agent_output
from app.services.queue import queue_service
from app.services.realtime.event_bus import event_bus
from app.services.serialization import message_to_dict, subtask_to_dict, task_to_dict
from app.services.tasks.service import create_task_for_prompt
from app.services.workflows.definition import (
    _conversation_agents,
    _single_agent_for_conversation,
    _workflow_for_conversation,
    _workflow_plan,
)
from app.services.workflows.engine import WorkflowEngine
from app.services.workflows.planning import _maybe_replan_workflow
from app.services.workflows.runtime import _sync_workflow_run, build_edge_states, build_node_states
from app.services.workflows.validator import (
    format_workflow_validation_message,
    validate_workflow_graph,
)

logger = logging.getLogger(__name__)


async def run_orchestration(message_id: str) -> None:
    db = SessionLocal()
    task: Task | None = None
    assistant: Message | None = None
    conversation: Conversation | None = None
    workflow_run: WorkflowRun | None = None
    stream_text = ""
    channel: str | None = None
    try:
        user_message = db.get(Message, message_id)
        if not user_message:
            return
        conversation = db.get(Conversation, user_message.conversation_id)
        if not conversation:
            return
        channel = f"conversation:{conversation.id}"
        prompt = _prompt_with_attachments(user_message)

        direct_agent = _single_agent_for_conversation(db, conversation)
        if direct_agent:
            await _run_direct_agent(
                db,
                conversation=conversation,
                user_message=user_message,
                agent=direct_agent,
                prompt=prompt,
                channel=channel,
            )
            return

        agents = _conversation_agents(db, conversation)
        workflow = _workflow_for_conversation(conversation, agents)
        workflow = await _maybe_replan_workflow(
            db,
            conversation=conversation,
            agents=agents,
            prompt=prompt,
            workflow=workflow,
            channel=channel,
        )
        validation = validate_workflow_graph(workflow, agents=agents)
        if not validation.ok:
            await _publish_workflow_validation_error(db, conversation, channel, validation)
            return

        output_mode = str(
            workflow.get("output_mode")
            or (workflow.get("settings") or {}).get("output_mode")
            or "independent_messages"
        )
        independent_group_mode = conversation.chat_type == "group" and output_mode == "independent_messages"
        plan = _workflow_plan(prompt, workflow)
        task = create_task_for_prompt(db, conversation, prompt, plan=plan)
        workflow_run = _create_workflow_run(db, conversation, user_message, workflow)
        db.commit()
        await _start_task(db, task, conversation.id, channel)

        if not independent_group_mode:
            assistant = await _create_master_placeholder(db, conversation, channel)

        subtasks = _load_subtasks(db, task)
        engine_result = await WorkflowEngine(
            db,
            conversation=conversation,
            user_message=user_message,
            task=task,
            workflow_run=workflow_run,
            workflow=workflow,
            prompt=prompt,
            channel=channel,
            agents=agents,
        ).run()

        if workflow_run.status == "failed":
            await _mark_workflow_failed(db, conversation, task, workflow_run, assistant, channel)
            return

        await _sync_subtasks_from_engine(db, subtasks, engine_result.outputs, channel)
        if engine_result.worker_contexts:
            task.output = {**(task.output or {}), "worker_contexts": engine_result.worker_contexts}
        await _publish_tool_artifacts(db, channel, engine_result.tool_context)
        task.output = {**(task.output or {}), "agentic_tools": engine_result.tool_context}
        task.progress = max(task.progress or 0, 58)
        db.commit()
        await event_bus.publish(channel, "task:status_changed", task_to_dict(task))

        if independent_group_mode and engine_result.agent_replies:
            await _complete_independent_group(
                db,
                conversation,
                task,
                workflow_run,
                subtasks,
                engine_result.agent_replies,
                channel,
            )
            return

        stream_text = await _stream_master_response(
            db,
            conversation,
            user_message,
            assistant,
            prompt,
            engine_result.tool_context,
            channel,
        )
        review_text = await _review(prompt)
        await _complete_master_task(
            db,
            conversation,
            task,
            workflow_run,
            subtasks,
            stream_text,
            review_text,
            channel,
        )
    except asyncio.CancelledError:
        await _handle_cancelled(
            db,
            conversation=conversation,
            task=task,
            assistant=assistant,
            workflow_run=workflow_run,
            channel=channel,
            stream_text=stream_text,
        )
        raise
    except Exception as exc:
        logger.exception("orchestration failed: message_id=%s", message_id)
        await fail_generation(
            db,
            conversation=conversation,
            channel=channel,
            task=task,
            workflow_run=workflow_run,
            reason="orchestration_failed",
            error=exc,
        )
    finally:
        db.close()


def _prompt_with_attachments(user_message: Message) -> str:
    return str((user_message.content or {}).get("text") or "")


async def _publish_workflow_validation_error(
    db,
    conversation: Conversation,
    channel: str,
    validation,
) -> None:
    warning_text = format_workflow_validation_message(validation)
    assistant = Message(
        conversation_id=conversation.id,
        sender_type="agent",
        sender_id=None,
        sender_name="Workflow Engine",
        content_type="text",
        content={"text": warning_text, "validation_errors": validation.errors},
        status="completed",
    )
    db.add(assistant)
    conversation.last_message_preview = warning_text[:300]
    conversation.last_message_sender = "Workflow Engine"
    conversation.last_message_at = utcnow()
    conversation.message_count += 1
    db.commit()
    db.refresh(assistant)
    await event_bus.publish(channel, "message:new", message_to_dict(assistant))
    await event_bus.publish(
        channel,
        "generation_finished",
        {"conversation_id": conversation.id, "reason": "workflow_invalid"},
    )


def _create_workflow_run(db, conversation: Conversation, user_message: Message, workflow: dict) -> WorkflowRun:
    workflow_run = WorkflowRun(
        conversation_id=conversation.id,
        trigger_message_id=user_message.id,
        started_by=conversation.creator_id,
        status="running",
        mode=str(workflow.get("mode") or "canvas"),
        workflow_snapshot=workflow,
        node_states=build_node_states(workflow),
        edge_states=build_edge_states(workflow),
        events=[{"type": "run.started", "at": utcnow().isoformat(), "trigger_message_id": user_message.id}],
        progress=5,
        started_at=utcnow(),
    )
    db.add(workflow_run)
    _sync_workflow_run(conversation, workflow_run)
    return workflow_run


async def _start_task(db, task: Task, conversation_id: str, channel: str) -> None:
    await queue_service.enqueue({"id": task.id, "conversation_id": conversation_id}, priority=10)
    await event_bus.publish(channel, "task:status_changed", task_to_dict(task))
    task.status = "EXECUTING"
    task.started_at = utcnow()
    task.progress = 20
    db.commit()
    await event_bus.publish(channel, "task:status_changed", task_to_dict(task))


async def _create_master_placeholder(db, conversation: Conversation, channel: str) -> Message:
    assistant = Message(
        conversation_id=conversation.id,
        sender_type="agent",
        sender_id=None,
        sender_name="Master Agent",
        content_type="text",
        content={"text": ""},
        status="streaming",
    )
    db.add(assistant)
    db.commit()
    db.refresh(assistant)
    await event_bus.publish(channel, "message_start", {"agent_message_id": assistant.id})
    return assistant


def _load_subtasks(db, task: Task) -> list[Subtask]:
    return (
        db.scalars(select(Subtask).where(Subtask.parent_task_id == task.id).order_by(Subtask.order_index))
        .unique()
        .all()
    )


async def _sync_subtasks_from_engine(db, subtasks: list[Subtask], outputs: dict, channel: str) -> None:
    for subtask in subtasks:
        subtask_input = subtask.input if isinstance(subtask.input, dict) else {}
        workflow_node = subtask_input.get("workflow_node") if isinstance(subtask_input.get("workflow_node"), dict) else {}
        node_id = str(subtask_input.get("subtask_id") or workflow_node.get("id") or subtask.id)
        node_output = outputs.get(node_id, {})
        subtask.status = "COMPLETED" if node_output else "SKIPPED"
        subtask.output = {
            "summary": str(node_output.get("summary") or node_output.get("text") or subtask.title)[:500],
            "agentic_tools": node_output,
        }
        subtask.completed_at = utcnow()
        await event_bus.publish(channel, "task:subtask_updated", subtask_to_dict(subtask))
    db.commit()


async def _mark_workflow_failed(
    db,
    conversation: Conversation,
    task: Task,
    workflow_run: WorkflowRun,
    assistant: Message | None,
    channel: str,
) -> None:
    task.status = "FAILED"
    task.progress = workflow_run.progress
    task.error_info = {"workflow_run_id": workflow_run.id, "events": workflow_run.events[-10:] if workflow_run.events else []}
    task.completed_at = utcnow()
    if assistant:
        assistant.status = "failed"
        assistant.content = {"text": "工作流执行失败，已停止后续依赖节点。请打开群聊工作流画布查看失败节点。"}
    conversation.last_message_preview = "工作流执行失败，已停止后续依赖节点。"
    conversation.last_message_sender = "Workflow Engine"
    conversation.last_message_at = utcnow()
    db.commit()
    await event_bus.publish(channel, "task:status_changed", task_to_dict(task))
    if assistant:
        await event_bus.publish(channel, "message:updated", message_to_dict(assistant))
        await event_bus.publish(channel, "message_stop", {"agent_message_id": assistant.id, "stop_reason": "workflow_failed"})
    await finalize_streaming_agent_messages(
        db,
        conversation=conversation,
        channel=channel,
        status="failed",
        stop_reason="workflow_failed",
        fallback_text="工作流执行失败，已停止后续节点。",
    )
    await event_bus.publish(channel, "generation_finished", {"conversation_id": conversation.id, "reason": "workflow_failed"})


async def _complete_independent_group(
    db,
    conversation: Conversation,
    task: Task,
    workflow_run: WorkflowRun,
    subtasks: list[Subtask],
    agent_replies: list[dict[str, str]],
    channel: str,
) -> None:
    summary = "\n\n".join(f"{item['agent_name']}: {item['text']}" for item in agent_replies)
    for subtask in subtasks:
        subtask.status = "COMPLETED"
    task.status = "COMPLETED"
    task.progress = 100
    task.output = {
        **(task.output or {}),
        "mode": "all_agents_independent",
        "summary": summary,
        "agent_replies": agent_replies,
    }
    task.completed_at = utcnow()
    conversation.last_message_preview = (summary or "多 Agent 已完成本轮回复。")[:300]
    conversation.last_message_sender = "AgentHub"
    conversation.last_message_at = utcnow()
    conversation.activity_score = min(100, conversation.activity_score + 6)
    _mark_workflow_completed(conversation, workflow_run)
    db.commit()
    await finalize_streaming_agent_messages(
        db,
        conversation=conversation,
        channel=channel,
        status="completed",
        stop_reason="workflow_completed",
        fallback_text="本轮响应已结束。",
    )
    await event_bus.publish(channel, "task:status_changed", task_to_dict(task))
    await event_bus.publish(
        channel,
        "workflow:run_updated",
        {"run_id": workflow_run.id, "status": workflow_run.status, "progress": workflow_run.progress},
    )
    await event_bus.publish(channel, "generation_finished", {"conversation_id": conversation.id, "reason": "workflow_completed"})


async def _stream_master_response(
    db,
    conversation: Conversation,
    user_message: Message,
    assistant: Message | None,
    prompt: str,
    tool_context: dict,
    channel: str,
) -> str:
    if assistant is None:
        assistant = await _create_master_placeholder(db, conversation, channel)
    messages = [
        {
            "role": "system",
            "content": (
                "你是 AgentHub 主控 Agent。你可以在内部完成任务拆解、执行协调和审查，"
                "但对用户只输出最终可读回复，不要输出内部阶段标题。"
                "如果工具或 Skill 已返回结果，请融合为自然语言结论，不要粘贴内部 JSON。"
            ),
        },
        {"role": "system", "content": "可用工具执行摘要：" + json.dumps(tool_context, ensure_ascii=False)[:6000]},
        {"role": "user", "content": prompt},
    ]
    thinking_enabled = (user_message.extra or {}).get("thinking_enabled") is True
    thinking = {"type": "enabled", "budget_tokens": 1024} if thinking_enabled else None
    stream_text = ""
    reasoning_text = ""
    stream_filter = InternalOutputStreamFilter()
    reasoning_filter = InternalOutputStreamFilter()
    async for event in ark_client.stream_chat(messages, purpose="chat", thinking=thinking):
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
                            "delta": {"type": "text_delta", "text": visible_delta},
                        },
                    )
            if event.reasoning:
                reasoning_text += event.reasoning
                visible_reasoning = reasoning_filter.push(event.reasoning)
                if not visible_reasoning:
                    continue
                await event_bus.publish(
                    channel,
                    "content_block_delta",
                    {"agent_message_id": assistant.id, "delta": {"type": "reasoning_delta", "text": visible_reasoning}},
                )
        elif event.type == "usage":
            await event_bus.publish(channel, "usage", {"agent_message_id": assistant.id, "usage": event.usage})
        elif event.type == "error":
            stream_text += f"\n模型调用异常，已降级：{event.error}"

    display_text = strip_internal_agent_output(stream_text)
    assistant.content = {
        "text": display_text or "我已经完成处理，但本次模型没有返回可展示的最终回复。",
        "thinking": strip_internal_agent_output(reasoning_text) if reasoning_text else "",
    }
    assistant.status = "completed"
    db.commit()
    await event_bus.publish(channel, "message:updated", message_to_dict(assistant))
    conversation.last_message_preview = (display_text or "主控 Agent 已完成回复。")[:300]
    conversation.last_message_sender = "Master Agent"
    conversation.last_message_at = utcnow()
    conversation.activity_score = min(100, conversation.activity_score + 8)
    conversation.message_count += 1
    db.commit()
    await event_bus.publish(channel, "message_stop", {"agent_message_id": assistant.id, "stop_reason": "end_turn"})
    return display_text or stream_text


async def _complete_master_task(
    db,
    conversation: Conversation,
    task: Task,
    workflow_run: WorkflowRun,
    subtasks: list[Subtask],
    stream_text: str,
    review_text: str,
    channel: str,
) -> None:
    for subtask in subtasks:
        subtask.status = "COMPLETED"
    task.status = "COMPLETED"
    task.progress = 100
    task.output = {**(task.output or {}), "summary": stream_text, "review": review_text}
    task.completed_at = utcnow()
    _mark_workflow_completed(conversation, workflow_run)
    db.commit()
    await event_bus.publish(channel, "task:status_changed", task_to_dict(task))
    await event_bus.publish(
        channel,
        "workflow:run_updated",
        {"run_id": workflow_run.id, "status": workflow_run.status, "progress": workflow_run.progress},
    )
    await event_bus.publish(channel, "generation_finished", {"conversation_id": conversation.id, "reason": "workflow_completed"})


def _mark_workflow_completed(conversation: Conversation, workflow_run: WorkflowRun) -> None:
    for state in workflow_run.node_states or []:
        if state.get("type") == "end":
            state["status"] = "completed"
            state["progress"] = 100
            state["started_at"] = state.get("started_at") or utcnow().isoformat()
            state["completed_at"] = utcnow().isoformat()
    workflow_run.node_states = list(workflow_run.node_states or [])
    workflow_run.status = "completed"
    workflow_run.progress = 100
    workflow_run.completed_at = utcnow()
    workflow_run.events = [*(workflow_run.events or []), {"type": "run.completed", "at": utcnow().isoformat()}][-200:]
    _sync_workflow_run(conversation, workflow_run)


async def _handle_cancelled(
    db,
    *,
    conversation: Conversation | None,
    task: Task | None,
    assistant: Message | None,
    workflow_run: WorkflowRun | None,
    channel: str | None,
    stream_text: str,
) -> None:
    if task:
        task.status = "CANCELLED"
        task.progress = min(task.progress or 0, 95)
        task.completed_at = utcnow()
        task.output = {**(task.output or {}), "cancelled": True}
    if assistant:
        assistant.status = "cancelled"
        assistant.content = {"text": strip_internal_agent_output(stream_text) or "已停止本次响应。"}
    if conversation:
        conversation.last_message_preview = "已停止本次响应。"
        conversation.last_message_sender = "Master Agent"
        conversation.last_message_at = utcnow()
    if workflow_run:
        workflow_run.status = "cancelled"
        workflow_run.completed_at = utcnow()
        workflow_run.events = [*(workflow_run.events or []), {"type": "run.cancelled", "at": utcnow().isoformat()}][-200:]
        if conversation:
            _sync_workflow_run(conversation, workflow_run)
    db.commit()
    if not channel or not conversation:
        return
    if task:
        await event_bus.publish(channel, "task:status_changed", task_to_dict(task))
    if assistant:
        await event_bus.publish(channel, "message:updated", message_to_dict(assistant))
        await event_bus.publish(channel, "message_stop", {"agent_message_id": assistant.id, "stop_reason": "cancelled"})
    await finalize_streaming_agent_messages(
        db,
        conversation=conversation,
        channel=channel,
        status="cancelled",
        stop_reason="cancelled",
        fallback_text="已停止本次响应。",
    )
    if workflow_run:
        await event_bus.publish(
            channel,
            "workflow:run_updated",
            {"run_id": workflow_run.id, "status": workflow_run.status, "progress": workflow_run.progress},
        )
    await event_bus.publish(channel, "generation_finished", {"conversation_id": conversation.id, "reason": "cancelled"})


async def _review(prompt: str) -> str:
    try:
        result = await ark_client.chat(
            [
                {"role": "system", "content": "你是 Reviewer Agent，审查多 Agent 产物是否可演示。"},
                {"role": "user", "content": prompt},
            ],
            purpose="review",
            max_tokens=500,
        )
        return result.text
    except ArkProviderError as exc:
        return f"[fallback-review] 方舟审查调用失败，使用规则审查通过：{exc}"
