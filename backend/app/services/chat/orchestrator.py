from __future__ import annotations

import asyncio
import json
from typing import Any

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models import Agent, Artifact, Conversation, Message, Subtask, Task, WorkflowRun, utcnow
from app.services.agents.direct import _run_direct_agent
from app.services.agents.function_loop import run_agent_function_call_loop
from app.services.ark import ArkProviderError, ark_client
from app.services.artifacts import build_demo_html, classify_artifact_request, create_artifact, create_preview_message
from app.services.chat.artifacts import _publish_tool_artifacts
from app.services.output_filter import strip_internal_agent_output
from app.services.queue import queue_service
from app.services.realtime.event_bus import event_bus
from app.services.serialization import artifact_to_dict, message_to_dict, subtask_to_dict, task_to_dict
from app.services.tasks.service import create_task_for_prompt
from app.services.workflows.definition import (
    _conversation_agents,
    _node_config,
    _single_agent_for_conversation,
    _workflow_for_conversation,
    _workflow_node_states,
    _workflow_node_type,
    _workflow_plan,
)
from app.services.workflows.planning import _maybe_replan_workflow
from app.services.workflows.runtime import _set_workflow_node_state, _sync_workflow_run


async def run_orchestration(message_id: str) -> None:
    db = SessionLocal()
    task: Task | None = None
    assistant: Message | None = None
    conversation: Conversation | None = None
    artifact = None
    preview_message = None
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
        prompt = user_message.content.get("text", "")
        attachments = user_message.content.get("attachments") or []
        if attachments:
            attachment_context = "\n\n".join(
                [
                    (
                        f"附件 {index}: {item.get('filename')} ({item.get('content_type')}, {item.get('size')} bytes)\n"
                        f"{item.get('extracted_text') or '[文件已上传，但当前解析器未提取文本]'}"
                    )
                    for index, item in enumerate(attachments, start=1)
                ]
            )
            prompt = f"{prompt}\n\n## 用户上传附件\n{attachment_context}"
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
        independent_group_mode = conversation.chat_type == "group" and str(workflow.get("mode") or "") == "all_agents_independent"
        independent_agent_replies: list[dict[str, str]] = []
        plan = _workflow_plan(prompt, workflow)
        task = create_task_for_prompt(db, conversation, prompt, plan=plan)
        workflow_run = WorkflowRun(
            conversation_id=conversation.id,
            trigger_message_id=user_message.id,
            started_by=conversation.creator_id,
            status="running",
            mode=str(workflow.get("mode") or "canvas"),
            workflow_snapshot=workflow,
            node_states=_workflow_node_states(workflow),
            edge_states=[
                {"from": edge[0], "to": edge[1], "status": "waiting"}
                for edge in workflow.get("edges", [])
                if isinstance(edge, list) and len(edge) == 2
            ],
            events=[{"type": "run.started", "at": utcnow().isoformat(), "trigger_message_id": user_message.id}],
            progress=5,
            started_at=utcnow(),
        )
        db.add(workflow_run)
        for state in workflow_run.node_states or []:
            if state.get("type") == "start":
                state["status"] = "completed"
                state["progress"] = 100
                state["started_at"] = utcnow().isoformat()
                state["completed_at"] = utcnow().isoformat()
        workflow_run.node_states = list(workflow_run.node_states or [])
        _sync_workflow_run(conversation, workflow_run)
        db.commit()
        await queue_service.enqueue({"id": task.id, "conversation_id": conversation.id}, priority=10)

        await event_bus.publish(channel, "task:status_changed", task_to_dict(task))
        await event_bus.publish(channel, "workflow:run_updated", {"run_id": workflow_run.id, "status": workflow_run.status, "progress": workflow_run.progress})

        task.status = "EXECUTING"
        task.started_at = utcnow()
        task.progress = 20
        db.commit()
        await event_bus.publish(channel, "task:status_changed", task_to_dict(task))

        # 非独立群聊模式下提前创建主控 Agent 占位消息，让前端立刻显示气泡
        if not independent_group_mode:
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

        artifact_type = classify_artifact_request(prompt)
        if artifact_type:
            existing_preview = db.scalar(
                select(Message)
                .where(
                    Message.conversation_id == conversation.id,
                    Message.content_type == "preview_card",
                    Message.created_at >= user_message.created_at,
                    Message.deleted_at.is_(None),
                )
                .order_by(Message.created_at.desc())
            )
            if existing_preview:
                preview_message = existing_preview
                artifact_id = existing_preview.content.get("artifact_id") if isinstance(existing_preview.content, dict) else None
                artifact = db.get(Artifact, artifact_id) if artifact_id else None
        subtasks = (
            db.scalars(select(Subtask).where(Subtask.parent_task_id == task.id).order_by(Subtask.order_index))
            .unique()
            .all()
        )
        worker_contexts: list[dict[str, Any]] = []
        for subtask in subtasks:
            subtask.status = "EXECUTING"
            subtask.started_at = utcnow()
            db.commit()
            await event_bus.publish(channel, "task:subtask_updated", subtask_to_dict(subtask))
            await asyncio.sleep(0.15)
            worker_context: dict[str, Any] = {}
            node = subtask.input.get("workflow_node") if isinstance(subtask.input, dict) else {}
            node = node if isinstance(node, dict) else {}
            node_type = _workflow_node_type(node)
            node_config = _node_config(node)
            node_id = str(node.get("id") or subtask.id)
            if workflow_run:
                _set_workflow_node_state(workflow_run, node_id, status="running", progress=30)
                _sync_workflow_run(conversation, workflow_run)
                db.commit()
                await event_bus.publish(channel, "workflow:run_updated", {"run_id": workflow_run.id, "status": workflow_run.status, "progress": workflow_run.progress, "node_id": node_id})
            agent_id = node.get("agent_id") or node_config.get("agent_id") or subtask.agent_id
            worker_agent = db.get(Agent, str(agent_id)) if agent_id else None
            if node_type in {"agent", "review"} and worker_agent and worker_agent.deleted_at is None:
                loop_result = await run_agent_function_call_loop(
                    db,
                    conversation=conversation,
                    user_message=user_message,
                    agent=worker_agent,
                    prompt=f"{prompt}\n\nWorkflow node: {subtask.title}\n{subtask.description}",
                    channel=channel,
                    mode="群聊工作流节点",
                    task=task,
                    workflow_run=workflow_run,
                    workflow_node_id=node_id,
                    node_title=subtask.title,
                    max_tool_rounds=3,
                )
                worker_context = loop_result.tool_context
                worker_contexts.append(
                    {
                        "subtask_id": subtask.id,
                        "subtask_title": subtask.title,
                        "agent_id": worker_agent.id,
                        "agent_name": worker_agent.name,
                        "context": worker_context,
                    }
                )
                await _publish_tool_artifacts(db, channel, worker_context)
                if independent_group_mode:
                    independent_agent_replies.append(
                        {"agent_id": worker_agent.id, "agent_name": worker_agent.name, "text": loop_result.text[:1000]}
                    )
            elif node_type == "condition":
                branches = node_config.get("branches") if isinstance(node_config.get("branches"), list) else ["true", "false"]
                matched = branches[0] if branches else "default"
                worker_context = {"mode": "condition", "expression": node_config.get("expression"), "matched_branch": matched}
            elif node_type == "loop":
                max_iterations = int(node_config.get("max_iterations") or 3)
                worker_context = {"mode": "loop", "max_iterations": max_iterations, "current_iteration": max_iterations}
            else:
                worker_context = {"mode": "canvas_node", "type": node_type, "config": node_config}
            subtask.status = "REVIEW_PENDING" if subtask.order_index < len(subtasks) - 1 else "REVIEWING"
            subtask.output = {
                "summary": f"{subtask.title} 已完成",
                "files": ["index.html"] if subtask.order_index == 0 else [],
                "agentic_tools": worker_context,
            }
            subtask.completed_at = utcnow()
            if workflow_run:
                node_output = worker_context if isinstance(worker_context, dict) else {"result": worker_context}
                _set_workflow_node_state(workflow_run, node_id, status="completed", progress=100, output=node_output)
                _sync_workflow_run(conversation, workflow_run)
            db.commit()
            await event_bus.publish(channel, "task:subtask_updated", subtask_to_dict(subtask))
            if workflow_run:
                await event_bus.publish(channel, "workflow:run_updated", {"run_id": workflow_run.id, "status": workflow_run.status, "progress": workflow_run.progress, "node_id": node_id})

        tool_context = {"mode": "canvas_first", "executions": [], "worker_contexts": worker_contexts, "summary": "workflow nodes executed"}
        if worker_contexts:
            tool_context = {**tool_context, "worker_contexts": worker_contexts}
            task.output = {**(task.output or {}), "worker_contexts": worker_contexts}
        await _publish_tool_artifacts(db, channel, tool_context)
        if tool_context["executions"]:
            task.output = {**(task.output or {}), "agentic_tools": tool_context}
            task.progress = 58
            db.commit()
            await event_bus.publish(channel, "task:status_changed", task_to_dict(task))

        if artifact_type:
            artifact_name = {
                "document": "AgentHub 文档产物预览",
                "spreadsheet": "AgentHub 表格产物预览",
                "slides": "AgentHub 演示文稿预览",
                "code": "AgentHub 代码产物预览",
                "web_app": "AgentHub Web 产物预览",
            }.get(artifact_type, "AgentHub 协作产物预览")
            artifact = create_artifact(
                db,
                conversation,
                task=task,
                name=artifact_name,
                html=build_demo_html(prompt, "主控 Agent 正在流式生成最终说明，产物已可先行预览。", artifact_type=artifact_type),
                artifact_type=artifact_type,
            )
            preview_message = create_preview_message(db, conversation, artifact)
            conversation.last_message_preview = "已生成产物卡片，可点击后在右侧预览、编辑和部署。"
            conversation.last_message_sender = "Artifact Agent"
            conversation.last_message_at = utcnow()
            conversation.message_count += 1
            db.commit()
            db.refresh(artifact)
            db.refresh(preview_message)
            await event_bus.publish(channel, "artifact:created", artifact_to_dict(artifact))
            await event_bus.publish(channel, "message:new", message_to_dict(preview_message))

        if independent_group_mode and independent_agent_replies:
            summary = "\n\n".join(f"{item['agent_name']}: {item['text']}" for item in independent_agent_replies)
            for subtask in subtasks:
                subtask.status = "COMPLETED"
            task.status = "COMPLETED"
            task.progress = 100
            task.output = {
                **(task.output or {}),
                "mode": "all_agents_independent",
                "summary": summary,
                "agent_replies": independent_agent_replies,
            }
            task.completed_at = utcnow()
            if workflow_run:
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
            db.commit()
            await event_bus.publish(channel, "task:status_changed", task_to_dict(task))
            if workflow_run:
                await event_bus.publish(channel, "workflow:run_updated", {"run_id": workflow_run.id, "status": workflow_run.status, "progress": workflow_run.progress})
            await event_bus.publish(channel, "message_stop", {"stop_reason": "all_agents_completed"})
            return

        messages = [
            {
                "role": "system",
                "content": (
                    "你是 AgentHub 主控 Agent。你可以在内部完成任务拆解、执行协调和审查，"
                    "但对用户只输出最终可读回复。不要输出“任务拆解”“执行过程”“合规审查”"
                    "等内部段落标题。普通问候直接友好回复并引导用户提出需求。"
                    "如果工具或 Skill 有返回结果，融合为自然语言结论，不要贴内部 JSON。"
                ),
            },
            {
                "role": "system",
                "content": "可用工具执行摘要："
                + json.dumps(tool_context, ensure_ascii=False)[:6000],
            },
            {"role": "user", "content": prompt},
        ]
        thinking_enabled = (user_message.extra or {}).get("thinking_enabled") is True
        thinking = {"type": "enabled", "budget_tokens": 1024} if thinking_enabled else None
        reasoning_text = ""
        async for event in ark_client.stream_chat(messages, purpose="chat", thinking=thinking):
            if event.type == "delta":
                if event.text:
                    stream_text += event.text
                    await event_bus.publish(
                        channel,
                        "content_block_delta",
                        {
                            "agent_message_id": assistant.id,
                            "delta": {"type": "text_delta", "text": event.text},
                        },
                    )
                if event.reasoning:
                    reasoning_text += event.reasoning
                    await event_bus.publish(
                        channel,
                        "content_block_delta",
                        {
                            "agent_message_id": assistant.id,
                            "delta": {"type": "reasoning_delta", "text": event.reasoning},
                        },
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

        created_preview_after_stream = False
        if artifact_type and not preview_message:
            artifact_name = {
                "document": "AgentHub 文档产物预览",
                "spreadsheet": "AgentHub 表格产物预览",
                "slides": "AgentHub 演示文稿预览",
                "code": "AgentHub 代码产物预览",
                "web_app": "AgentHub Web 产物预览",
            }.get(artifact_type, "AgentHub 协作产物预览")
            artifact = create_artifact(
                db,
                conversation,
                task=task,
                name=artifact_name,
                html=build_demo_html(prompt, "Reviewer 正在审查，稍后同步最终结论。", artifact_type=artifact_type),
                artifact_type=artifact_type,
            )
            preview_message = create_preview_message(db, conversation, artifact)
            conversation.last_message_preview = "已生成产物卡片，可点击后在右侧预览、编辑和部署。"
            created_preview_after_stream = True
        else:
            conversation.last_message_preview = (display_text or "主控 Agent 已完成回复。")[:300]
        conversation.last_message_sender = "Master Agent"
        conversation.last_message_at = utcnow()
        conversation.activity_score = min(100, conversation.activity_score + 8)
        conversation.message_count += 2 if created_preview_after_stream else 1
        db.commit()
        if created_preview_after_stream and preview_message:
            db.refresh(artifact)
            db.refresh(preview_message)
            await event_bus.publish(channel, "artifact:created", artifact_to_dict(artifact))
            await event_bus.publish(channel, "message:new", message_to_dict(preview_message))
        await event_bus.publish(channel, "message_stop", {"agent_message_id": assistant.id, "stop_reason": "end_turn"})

        review_text = await _review(prompt)
        for subtask in subtasks:
            subtask.status = "COMPLETED"
        task.status = "COMPLETED"
        task.progress = 100
        task.output = {
            **(task.output or {}),
            "summary": display_text or strip_internal_agent_output(stream_text),
            "review": review_text,
        }
        task.completed_at = utcnow()
        if workflow_run:
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
        db.commit()
        await event_bus.publish(channel, "task:status_changed", task_to_dict(task))
        if workflow_run:
            await event_bus.publish(channel, "workflow:run_updated", {"run_id": workflow_run.id, "status": workflow_run.status, "progress": workflow_run.progress})
    except asyncio.CancelledError:
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
        if channel:
            if task:
                await event_bus.publish(channel, "task:status_changed", task_to_dict(task))
            if assistant:
                await event_bus.publish(channel, "message:updated", message_to_dict(assistant))
                await event_bus.publish(channel, "message_stop", {"agent_message_id": assistant.id, "stop_reason": "cancelled"})
            if workflow_run:
                await event_bus.publish(channel, "workflow:run_updated", {"run_id": workflow_run.id, "status": workflow_run.status, "progress": workflow_run.progress})
        raise
    finally:
        db.close()


async def _review(prompt: str) -> str:
    try:
        result = await ark_client.chat(
            [
                {"role": "system", "content": "你是 Reviewer Agent，审查多Agent产物是否可演示。"},
                {"role": "user", "content": prompt},
            ],
            purpose="review",
            max_tokens=500,
        )
        return result.text
    except ArkProviderError as exc:
        return f"[fallback-review] 方舟审查调用失败，使用规则审查通过：{exc}"
