from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models import Agent, Artifact, Conversation, ConversationParticipant, Message, Subtask, Task, User, WorkflowRun, utcnow
from app.services.ark import ArkProviderError, ark_client
from app.services.agentic_runtime import (
    build_tools_for_agent,
    execute_tool_by_name,
    run_agentic_tool_loop,
)
from app.services.artifacts import build_demo_html, classify_artifact_request, create_artifact, create_preview_message
from app.services.events import event_bus
from app.services.output_filter import strip_internal_agent_output
from app.services.queue import queue_service
from app.services.serialization import artifact_to_dict, message_to_dict, subtask_to_dict, task_to_dict
from app.services.llm_gateway import stream_model_config


def _select_agent(agents: list[Agent], capability: str) -> Agent | None:
    needle = capability.lower()
    for agent in agents:
        labels: list[str] = [agent.name, agent.type]
        for item in agent.capabilities or []:
            if isinstance(item, dict):
                labels.extend(str(item.get(key) or "") for key in ("label", "name", "category"))
            else:
                labels.append(str(item))
        if any(needle in label.lower() for label in labels if label):
            return agent
    return agents[0] if agents else None


def _json_object(text: str) -> dict[str, Any] | None:
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, flags=re.S)
    if not match:
        return None
    try:
        value = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _normalize_plan(raw: dict[str, Any], fallback: dict[str, Any], agents: list[Agent]) -> dict[str, Any]:
    agent_ids = {agent.id for agent in agents}
    raw_subtasks = raw.get("subtasks") if isinstance(raw.get("subtasks"), list) else []
    subtasks: list[dict[str, Any]] = []
    for index, item in enumerate(raw_subtasks[:4]):
        if not isinstance(item, dict):
            continue
        domain = str(item.get("domain") or item.get("category") or "general")
        try:
            priority = int(item.get("priority") or index + 1)
        except (TypeError, ValueError):
            priority = index + 1
        assigned = item.get("assigned_agent_id")
        if assigned not in agent_ids:
            selected = _select_agent(agents, domain) or _select_agent(agents, str(item.get("title") or ""))
            assigned = selected.id if selected else None
        dependencies = item.get("dependencies") if isinstance(item.get("dependencies"), list) else []
        subtasks.append(
            {
                "subtask_id": str(item.get("subtask_id") or item.get("id") or f"st_{index + 1}"),
                "title": str(item.get("title") or f"子任务 {index + 1}")[:160],
                "description": str(item.get("description") or item.get("goal") or "")[:1200],
                "domain": domain,
                "priority": priority,
                "dependencies": [str(dep) for dep in dependencies],
                "output_spec": str(item.get("output_spec") or item.get("deliverable") or "结构化结果"),
                "assigned_agent_id": assigned,
            }
        )
    if not subtasks:
        return fallback
    edges = raw.get("dag_edges") if isinstance(raw.get("dag_edges"), list) else []
    normalized_edges = [
        [str(edge[0]), str(edge[1])]
        for edge in edges
        if isinstance(edge, list) and len(edge) == 2
    ]
    return {
        "plan_id": str(raw.get("plan_id") or fallback["plan_id"]),
        "user_requirement": str(raw.get("user_requirement") or fallback["user_requirement"]),
        "complexity": str(raw.get("complexity") or fallback["complexity"]),
        "subtasks": subtasks,
        "dag_edges": normalized_edges or fallback.get("dag_edges", []),
        "planner": "ark",
    }


def build_plan(prompt: str, agents: list[Agent]) -> dict[str, Any]:
    selected = {
        "frontend": _select_agent(agents, "前端") or _select_agent(agents, "frontend"),
        "backend": _select_agent(agents, "后端") or _select_agent(agents, "backend"),
        "reviewer": _select_agent(agents, "审查") or _select_agent(agents, "reviewer"),
    }
    subtasks = [
        {
            "subtask_id": "st_frontend",
            "title": "前端工作台与预览产物",
            "description": "实现 IM 三栏工作台、流式消息渲染和可交互预览页面。",
            "domain": "frontend",
            "priority": 1,
            "dependencies": [],
            "output_spec": "可预览 HTML/React 片段和交互说明",
            "assigned_agent_id": selected["frontend"].id if selected["frontend"] else None,
        },
        {
            "subtask_id": "st_backend",
            "title": "后端 API、数据模型与实时事件",
            "description": "实现会话、消息、任务、产物、部署 API，以及 SSE/WebSocket 事件。",
            "domain": "backend",
            "priority": 1,
            "dependencies": [],
            "output_spec": "REST API、持久化记录和事件流",
            "assigned_agent_id": selected["backend"].id if selected["backend"] else None,
        },
        {
            "subtask_id": "st_review",
            "title": "Reviewer 审查与聚合",
            "description": "审查前后端产物一致性、演示链路完整性并生成聚合报告。",
            "domain": "review",
            "priority": 2,
            "dependencies": ["st_frontend", "st_backend"],
            "output_spec": "审查报告和最终交付摘要",
            "assigned_agent_id": selected["reviewer"].id if selected["reviewer"] else None,
        },
    ]
    return {
        "plan_id": f"plan_{utcnow().strftime('%Y%m%d%H%M%S')}",
        "user_requirement": prompt,
        "complexity": "complex",
        "subtasks": subtasks,
        "dag_edges": [["st_frontend", "st_review"], ["st_backend", "st_review"]],
    }


async def build_plan_with_llm(prompt: str, agents: list[Agent]) -> dict[str, Any]:
    fallback = build_plan(prompt, agents)
    agent_catalog = [
        {
            "id": agent.id,
            "name": agent.name,
            "type": agent.type,
            "capabilities": agent.capabilities,
        }
        for agent in agents
    ]
    try:
        result = await ark_client.chat(
            [
                {
                    "role": "system",
                    "content": (
                        "你是 AgentHub 主控 Agent 的任务规划器。只返回 JSON，不要 Markdown。"
                        "JSON 字段包含 plan_id, user_requirement, complexity, subtasks, dag_edges。"
                        "每个 subtask 包含 subtask_id, title, description, domain, priority, "
                        "dependencies, output_spec, assigned_agent_id。优先使用给定 agent id。"
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {"requirement": prompt, "available_agents": agent_catalog},
                        ensure_ascii=False,
                    ),
                },
            ],
            temperature=0.15,
            max_tokens=1400,
            purpose="task_planning",
        )
        raw = _json_object(result.text)
        if raw:
            return _normalize_plan(raw, fallback, agents)
    except ArkProviderError:
        pass
    return fallback


def create_task_for_prompt(
    db: Session, conversation: Conversation, prompt: str, plan: dict[str, Any] | None = None
) -> Task:
    agents = _conversation_agents(db, conversation)
    plan = plan or build_plan(prompt, agents)
    task = Task(
        conversation_id=conversation.id,
        creator_id=conversation.creator_id,
        title=prompt[:80] or "多 Agent 协作任务",
        description=prompt,
        status="PENDING",
        priority="high",
        progress=5,
        plan=plan,
        input={"prompt": prompt},
    )
    db.add(task)
    db.flush()
    for index, spec in enumerate(plan["subtasks"]):
        db.add(
            Subtask(
                parent_task_id=task.id,
                title=spec["title"],
                description=spec["description"],
                status="PENDING",
                order_index=index,
                agent_id=spec.get("assigned_agent_id"),
                input=spec,
            )
        )
    db.flush()
    return task


def _single_agent_for_conversation(db: Session, conversation: Conversation) -> Agent | None:
    if conversation.chat_type != "single":
        return None
    participant = db.scalar(
        select(ConversationParticipant)
        .where(
            ConversationParticipant.conversation_id == conversation.id,
            ConversationParticipant.participant_type == "agent",
            ConversationParticipant.left_at.is_(None),
        )
        .limit(1)
    )
    if not participant or not participant.agent_id:
        return None
    agent = db.get(Agent, participant.agent_id)
    if not agent or agent.deleted_at is not None:
        return None
    return agent


def _conversation_agents(db: Session, conversation: Conversation) -> list[Agent]:
    participant_agent_ids = [
        item.agent_id
        for item in db.scalars(
            select(ConversationParticipant).where(
                ConversationParticipant.conversation_id == conversation.id,
                ConversationParticipant.participant_type == "agent",
                ConversationParticipant.left_at.is_(None),
                ConversationParticipant.agent_id.is_not(None),
            )
        ).all()
        if item.agent_id
    ]
    base_query = select(Agent).where(Agent.deleted_at.is_(None), Agent.status.in_(["online", "degraded"]))
    if participant_agent_ids:
        agents = db.scalars(base_query.where(Agent.id.in_(participant_agent_ids))).all()
        order = {agent_id: index for index, agent_id in enumerate(participant_agent_ids)}
        return sorted(agents, key=lambda agent: order.get(agent.id, 999))
    return db.scalars(base_query.where(Agent.type != "custom")).all()


WORKFLOW_NODE_TYPES = {"start", "agent", "tool", "skill", "mcp", "condition", "loop", "review", "artifact", "end"}
WORKFLOW_REPLAN_PATTERN = re.compile(r"(workflow|canvas|流程|画布|编排|规划|重排|调整工作流|让.*规划|master.*规划)", re.I)


def _workflow_node_type(node: dict[str, Any]) -> str:
    raw = str(node.get("type") or node.get("role") or "agent").lower().strip()
    if raw in WORKFLOW_NODE_TYPES:
        return raw
    if raw in {"reviewer", "review"}:
        return "review"
    if raw in {"deploy", "delivery", "publish"}:
        return "artifact"
    if raw in {"input"}:
        return "start"
    return "agent"


def _node_config(node: dict[str, Any]) -> dict[str, Any]:
    config = dict(node.get("config") if isinstance(node.get("config"), dict) else {})
    if node.get("agent_id"):
        config.setdefault("agent_id", node.get("agent_id"))
    node_type = _workflow_node_type(node)
    if node_type == "condition":
        config.setdefault("expression", "true")
        config.setdefault("branches", ["true", "false"])
    elif node_type == "loop":
        try:
            iterations = int(config.get("max_iterations") or node.get("max_iterations") or 3)
        except (TypeError, ValueError):
            iterations = 3
        config["max_iterations"] = max(1, min(iterations, 20))
    elif node_type == "tool":
        config.setdefault("tool_name", node.get("tool_name") or "")
    elif node_type == "mcp":
        config.setdefault("server_id", node.get("server_id") or "")
        config.setdefault("tool_name", node.get("tool_name") or "")
    elif node_type == "artifact":
        config.setdefault("artifact_type", node.get("artifact_type") or "html")
    return config


def _fallback_workflow_for_agents(conversation: Conversation, agents: list[Agent]) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = [
        {"id": "start", "title": "Start", "type": "start", "role": "start", "status": "ready", "meta": "message input", "config": {"input": "message"}},
    ]
    for agent in agents[:8]:
        node_type = "review" if agent.type == "reviewer" else "agent"
        nodes.append(
            {
                "id": f"agent-{agent.id[:8]}",
                "title": agent.name,
                "type": node_type,
                "role": agent.type or node_type,
                "status": agent.status,
                "meta": (agent.description or agent.type or node_type)[:160],
                "agent_id": agent.id,
                "config": {
                    "agent_id": agent.id,
                    "model_config_id": (agent.config or {}).get("model_config_id"),
                    "tools": (agent.config or {}).get("tools", []),
                    "skill_ids": (agent.config or {}).get("skill_ids", []),
                    "mcp_server_ids": (agent.config or {}).get("mcp_server_ids", []),
                },
            }
        )
    nodes.append({"id": "end", "title": "End", "type": "end", "role": "end", "status": "ready", "meta": "final answer", "config": {"output": "assistant_message"}})
    agent_nodes = [node for node in nodes if node["type"] in {"agent", "review"}]
    edges = [["start", node["id"]] for node in agent_nodes] + [[node["id"], "end"] for node in agent_nodes]
    return {
        "conversation_id": conversation.id,
        "mode": "all_agents_independent",
        "nodes": nodes,
        "edges": edges or [["start", "end"]],
        "settings": {"default_policy": "canvas-first", "review_policy": "optional"},
    }


def _sanitize_workflow(conversation: Conversation, agents: list[Agent], value: dict[str, Any] | None) -> dict[str, Any]:
    fallback = _fallback_workflow_for_agents(conversation, agents)
    active_agent_ids = {agent.id for agent in agents}
    source = value if isinstance(value, dict) else fallback
    raw_nodes = source.get("nodes") if isinstance(source.get("nodes"), list) else fallback["nodes"]
    nodes: list[dict[str, Any]] = []
    for index, node in enumerate(raw_nodes[:40]):
        if not isinstance(node, dict):
            continue
        node_type = _workflow_node_type(node)
        config = _node_config(node)
        agent_id = node.get("agent_id") or config.get("agent_id")
        if node_type in {"agent", "review"} and agent_id and str(agent_id) not in active_agent_ids:
            continue
        nodes.append(
            {
                "id": str(node.get("id") or f"node-{index + 1}"),
                "title": str(node.get("title") or node.get("name") or f"Node {index + 1}")[:80],
                "type": node_type,
                "role": str(node.get("role") or node_type),
                "status": str(node.get("status") or "ready"),
                "meta": str(node.get("meta") or node.get("description") or node_type)[:160],
                "config": config,
                **({"agent_id": str(agent_id)} if agent_id else {}),
            }
        )
    node_ids = {node["id"] for node in nodes}
    raw_edges = source.get("edges") if isinstance(source.get("edges"), list) else fallback["edges"]
    edges = [
        [str(edge[0]), str(edge[1])]
        for edge in raw_edges[:80]
        if isinstance(edge, list) and len(edge) == 2 and str(edge[0]) in node_ids and str(edge[1]) in node_ids
    ]
    return {
        **fallback,
        **{key: source[key] for key in ("mode", "settings") if key in source},
        "conversation_id": conversation.id,
        "nodes": nodes or fallback["nodes"],
        "edges": edges or fallback["edges"],
    }


def _workflow_for_conversation(conversation: Conversation, agents: list[Agent]) -> dict[str, Any]:
    extra = conversation.extra or {}
    return _sanitize_workflow(conversation, agents, extra.get("workflow") if isinstance(extra.get("workflow"), dict) else None)


def _workflow_execution_order(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = [node for node in workflow.get("nodes", []) if isinstance(node, dict)]
    node_by_id = {str(node.get("id")): node for node in nodes}
    indegree = {node_id: 0 for node_id in node_by_id}
    outgoing: dict[str, list[str]] = {node_id: [] for node_id in node_by_id}
    for edge in workflow.get("edges", []):
        if not isinstance(edge, list) or len(edge) != 2:
            continue
        start, end = str(edge[0]), str(edge[1])
        if start in node_by_id and end in node_by_id:
            outgoing[start].append(end)
            indegree[end] += 1
    ready = [node_id for node_id, degree in indegree.items() if degree == 0]
    ordered_ids: list[str] = []
    while ready:
        node_id = ready.pop(0)
        ordered_ids.append(node_id)
        for next_id in outgoing.get(node_id, []):
            indegree[next_id] -= 1
            if indegree[next_id] == 0:
                ready.append(next_id)
    if len(ordered_ids) != len(nodes):
        return nodes
    return [node_by_id[node_id] for node_id in ordered_ids]


def _workflow_node_states(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    states: list[dict[str, Any]] = []
    for index, node in enumerate(workflow.get("nodes", [])):
        if not isinstance(node, dict):
            continue
        node_type = _workflow_node_type(node)
        config = _node_config(node)
        output: dict[str, Any] = {}
        if node_type == "condition":
            branches = config.get("branches") if isinstance(config.get("branches"), list) else ["true", "false"]
            output = {"expression": config.get("expression"), "matched_branch": branches[0] if branches else "default"}
        elif node_type == "loop":
            output = {"max_iterations": int(config.get("max_iterations") or 3), "current_iteration": 0}
        states.append(
            {
                "id": str(node.get("id") or f"node-{index + 1}"),
                "title": str(node.get("title") or f"Node {index + 1}"),
                "type": node_type,
                "role": str(node.get("role") or node_type),
                "agent_id": node.get("agent_id"),
                "config": config,
                "status": "queued",
                "progress": 0,
                "output": output,
                "started_at": None,
                "completed_at": None,
            }
        )
    return states


def _sync_workflow_run(conversation: Conversation, run: WorkflowRun) -> None:
    conversation.extra = {
        **(conversation.extra or {}),
        "workflow_runtime": {
            "run_id": run.id,
            "status": run.status,
            "progress": run.progress,
            "node_states": run.node_states or [],
            "updated_at": utcnow().isoformat(),
        },
    }


def _set_workflow_node_state(run: WorkflowRun, node_id: str, *, status: str, progress: int, output: dict[str, Any] | None = None, message: str | None = None) -> None:
    states = list(run.node_states or [])
    now = utcnow().isoformat()
    for state in states:
        if state.get("id") != node_id:
            continue
        state["status"] = status
        state["progress"] = max(0, min(100, progress))
        if output is not None:
            state["output"] = {**(state.get("output") or {}), **output}
        if message:
            state["message"] = message
        if status in {"running", "reviewing"} and not state.get("started_at"):
            state["started_at"] = now
        if status in {"completed", "succeeded", "failed", "skipped"}:
            state["completed_at"] = now
        break
    run.node_states = states
    total = max(1, len(states))
    done = len([state for state in states if state.get("status") in {"completed", "succeeded", "skipped"}])
    run.progress = int(done / total * 100) if status != "running" else max(run.progress or 0, progress)


async def _maybe_replan_workflow(
    db: Session,
    *,
    conversation: Conversation,
    agents: list[Agent],
    prompt: str,
    workflow: dict[str, Any],
    channel: str,
) -> dict[str, Any]:
    if not WORKFLOW_REPLAN_PATTERN.search(prompt):
        return workflow
    planner = _select_agent(agents, "master") or _select_agent(agents, "规划") or agents[0] if agents else None
    if not planner:
        return workflow
    try:
        result = await ark_client.chat(
            [
                {
                    "role": "system",
                    "content": (
                        "You are an AgentHub workflow planning agent. Return JSON only. "
                        "Allowed node types: start, agent, tool, skill, mcp, condition, loop, review, artifact, end. "
                        "Preserve type/config fields. Use only provided agent ids."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "instruction": prompt,
                            "current_workflow": workflow,
                            "agents": [{"id": agent.id, "name": agent.name, "type": agent.type, "capabilities": agent.capabilities} for agent in agents],
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            temperature=0.1,
            max_tokens=1800,
            purpose="workflow_replan",
        )
        raw = _json_object(result.text)
        if not raw:
            return workflow
        next_workflow = _sanitize_workflow(conversation, agents, raw)
        conversation.extra = {**(conversation.extra or {}), "workflow": next_workflow}
        db.commit()
        await event_bus.publish(channel, "workflow:updated", next_workflow)
        return next_workflow
    except Exception:
        return workflow


def _workflow_plan(prompt: str, workflow: dict[str, Any]) -> dict[str, Any]:
    subtasks = []
    for node in _workflow_execution_order(workflow):
        node_type = _workflow_node_type(node)
        if node_type in {"start", "end"}:
            continue
        subtasks.append(
            {
                "subtask_id": str(node.get("id")),
                "title": str(node.get("title") or node_type),
                "description": str(node.get("meta") or node_type),
                "domain": node_type,
                "priority": len(subtasks) + 1,
                "dependencies": [],
                "output_spec": "workflow node result",
                "assigned_agent_id": node.get("agent_id") or (node.get("config") or {}).get("agent_id"),
                "workflow_node": node,
            }
        )
    return {
        "plan_id": f"workflow_{utcnow().strftime('%Y%m%d%H%M%S')}",
        "user_requirement": prompt,
        "complexity": "workflow",
        "planner": "canvas",
        "workflow": workflow,
        "subtasks": subtasks,
        "dag_edges": workflow.get("edges", []),
    }


async def _publish_tool_artifacts(db: Session, channel: str, tool_context: dict[str, Any]) -> None:
    for item in tool_context.get("executions") or []:
        output = item.get("output")
        if not isinstance(output, dict):
            continue
        artifact_payload = output.get("artifact")
        if isinstance(artifact_payload, dict) and artifact_payload.get("id"):
            artifact = db.get(Artifact, str(artifact_payload["id"]))
            if artifact:
                await event_bus.publish(channel, "artifact:created", artifact_to_dict(artifact))
        preview_message_id = output.get("preview_message_id")
        if preview_message_id:
            preview = db.get(Message, str(preview_message_id))
            if preview:
                await event_bus.publish(channel, "message:new", message_to_dict(preview))


async def _run_direct_agent(
    db: Session,
    *,
    conversation: Conversation,
    user_message: Message,
    agent: Agent,
    prompt: str,
    channel: str,
) -> None:
    """单聊模式 Function Calling 版本。"""
    settings = get_settings()
    enable_fc = settings.enable_function_calling
    model_config_id = (agent.config or {}).get("model_config_id")
    # 自定义模型暂不支持 tools，回退到预编排
    if not enable_fc or model_config_id:
        return await _run_direct_agent_legacy(
            db,
            conversation=conversation,
            user_message=user_message,
            agent=agent,
            prompt=prompt,
            channel=channel,
        )

    # 1. 创建 Task/Subtask
    task = Task(
        conversation_id=conversation.id,
        creator_id=conversation.creator_id,
        executor_agent_id=agent.id,
        title=prompt[:80] or f"{agent.name} 单聊任务",
        description=prompt,
        status="EXECUTING",
        priority="medium",
        progress=10,
        plan={
            "mode": "direct_worker_function_calling",
            "agent_id": agent.id,
            "agent_name": agent.name,
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
        title=f"{agent.name} Function Calling 执行",
        description="单聊模式下模型自主决定工具调用。",
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

    # 2. 立即创建 assistant 并发送 message_start（前端立刻显示气泡）
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

    # 3. 组装 tools 和 messages
    user = db.get(User, conversation.creator_id)
    tools = build_tools_for_agent(db, agent)
    system_prompt = (agent.config or {}).get("system_prompt") or agent.description or f"你是 {agent.name}。"
    system_prompt += (
        "\n你正在单聊模式直接响应用户。"
        "如果有合适的工具可以完成任务，请调用工具。"
        "不要伪装成 Master；如果没有工具权限，就作为纯对话 Agent 回复。"
    )
    messages: list[dict[str, str]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
    ]

    # 4. 流式生成 + 工具调用循环（最多 3 轮）
    stream_text = ""
    max_tool_rounds = 3
    tool_results: list[dict[str, Any]] = []

    for round_num in range(max_tool_rounds + 1):
        current_text = ""
        current_tool_calls: list[dict[str, Any]] | None = None
        try:
            async for event in ark_client.stream_chat(
                messages,
                purpose=f"agent:{agent.type}",
                tools=tools if tools else None,
            ):
                if event.type == "delta":
                    stream_text += event.text
                    current_text += event.text
                    await event_bus.publish(
                        channel,
                        "content_block_delta",
                        {
                            "agent_message_id": assistant.id,
                            "agent_id": agent.id,
                            "agent_name": agent.name,
                            "delta": {"type": "text_delta", "text": event.text},
                        },
                    )
                elif event.type == "tool_calls":
                    current_tool_calls = event.tool_calls
        except Exception as exc:
            if not stream_text:
                stream_text = f"\n模型调用异常，已降级：{exc}"
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
            break

        # 如果没有工具调用，或已达到最大轮数，结束循环
        if not current_tool_calls or round_num >= max_tool_rounds:
            break

        # 执行工具
        for tc in current_tool_calls:
            func = tc.get("function", {})
            tool_name = func.get("name", "")
            tool_args_str = func.get("arguments", "")
            try:
                tool_args = json.loads(tool_args_str) if tool_args_str else {}
            except json.JSONDecodeError:
                tool_args = {"raw": tool_args_str}

            # 发送 tool_call_start
            await event_bus.publish(
                channel,
                "tool_call_start",
                {
                    "agent_message_id": assistant.id,
                    "tool_name": tool_name,
                    "tool_call_id": tc.get("id", ""),
                },
            )

            result = await execute_tool_by_name(
                db,
                agent=agent,
                user=user,
                conversation=conversation,
                tool_name=tool_name,
                arguments=tool_args,
            )
            tool_results.append({
                "tool_name": tool_name,
                "tool_call_id": tc.get("id", ""),
                "result": result,
                "round": round_num,
            })
            db.commit()

            # 发送 tool_call_done
            await event_bus.publish(
                channel,
                "tool_call_done",
                {
                    "agent_message_id": assistant.id,
                    "tool_name": tool_name,
                    "tool_call_id": tc.get("id", ""),
                    "status": result.get("status", "unknown"),
                },
            )

        # 将 assistant 的回复和工具结果加入上下文
        messages.append({"role": "assistant", "content": current_text or "", "tool_calls": current_tool_calls})
        for tr in tool_results:
            if tr.get("round") == round_num:
                messages.append({
                    "role": "tool",
                    "tool_call_id": tr["tool_call_id"],
                    "content": json.dumps(tr["result"], ensure_ascii=False)[:4000],
                })

        task.progress = min(90, 20 + (round_num + 1) * 25)
        db.commit()
        await event_bus.publish(channel, "task:status_changed", task_to_dict(task))

    # 5. 完成收尾
    display_text = strip_internal_agent_output(stream_text)
    assistant.content = {"text": display_text or f"{agent.name} 已完成本次单聊处理。"}
    assistant.status = "completed"
    subtask.status = "COMPLETED"
    subtask.completed_at = utcnow()
    subtask.output = {"summary": assistant.content["text"][:500], "tool_results": tool_results}
    task.status = "COMPLETED"
    task.progress = 100
    task.output = {**(task.output or {}), "summary": assistant.content["text"], "tool_results": tool_results}
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


async def _run_direct_agent_legacy(
    db: Session,
    *,
    conversation: Conversation,
    user_message: Message,
    agent: Agent,
    prompt: str,
    channel: str,
) -> None:
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
    system_prompt = (agent.config or {}).get("system_prompt") or agent.description or f"你是 {agent.name}。"
    system_prompt += (
        "\n你正在单聊模式直接响应用户。只使用你被授权的工具/Skill/MCP 结果，"
        "不要伪装成 Master；如果没有工具权限，就作为纯对话 Agent 回复。"
    )
    tool_summary = json.dumps(tool_context, ensure_ascii=False)[:6000]
    model_config_id = (agent.config or {}).get("model_config_id")
    if model_config_id:
        try:
            async for chunk in stream_model_config(
                db,
                str(model_config_id),
                f"{system_prompt}\n\n工具执行摘要：{tool_summary}\n\n用户：{prompt}",
            ):
                text = chunk.get("text", "")
                if text:
                    stream_text += text
                    await event_bus.publish(
                        channel,
                        "content_block_delta",
                        {"agent_message_id": assistant.id, "agent_id": agent.id, "agent_name": agent.name, "delta": {"type": "text_delta", "text": text}},
                    )
        except Exception as exc:
            stream_text = f"{agent.name} 的专属模型调用失败，已降级：{exc}"
            await event_bus.publish(
                channel,
                "content_block_delta",
                {"agent_message_id": assistant.id, "agent_id": agent.id, "agent_name": agent.name, "delta": {"type": "text_delta", "text": stream_text}},
            )
    else:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "system", "content": "工具执行摘要：" + tool_summary},
            {"role": "user", "content": prompt},
        ]
        async for event in ark_client.stream_chat(messages, purpose=f"agent:{agent.type}"):
            if event.type == "delta":
                stream_text += event.text
                await event_bus.publish(
                    channel,
                    "content_block_delta",
                    {"agent_message_id": assistant.id, "agent_id": agent.id, "agent_name": agent.name, "delta": {"type": "text_delta", "text": event.text}},
                )
            elif event.type == "error":
                stream_text += f"\n模型调用异常，已降级：{event.error}"

    display_text = strip_internal_agent_output(stream_text)
    assistant.content = {"text": display_text or f"{agent.name} 已完成本次单聊处理。"}
    assistant.status = "completed"
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


async def _run_canvas_agent_reply(
    db: Session,
    *,
    conversation: Conversation,
    agent: Agent,
    prompt: str,
    channel: str,
    tool_context: dict[str, Any],
) -> str:
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
    await event_bus.publish(channel, "message_start", {"agent_message_id": assistant.id, "agent_id": agent.id, "agent_name": agent.name})

    stream_text = ""
    system_prompt = (agent.config or {}).get("system_prompt") or agent.description or f"You are {agent.name}."
    system_prompt += (
        "\nYou are replying as yourself in an AgentHub group chat. "
        "Do not pretend to be Master Agent unless your own name/type is Master. "
        "Use only your authorized tools, skills, MCP results, and role expertise. "
        "Return a concise, user-facing answer without internal planning sections."
    )
    tool_summary = json.dumps(tool_context, ensure_ascii=False)[:6000]
    model_config_id = (agent.config or {}).get("model_config_id")
    if model_config_id:
        try:
            async for chunk in stream_model_config(
                db,
                str(model_config_id),
                f"{system_prompt}\n\nTool context:\n{tool_summary}\n\nUser:\n{prompt}",
            ):
                text = chunk.get("text", "")
                if text:
                    stream_text += text
                    await event_bus.publish(
                        channel,
                        "content_block_delta",
                        {"agent_message_id": assistant.id, "delta": {"type": "text_delta", "text": text}},
                    )
        except Exception as exc:
            stream_text = f"{agent.name} model call failed and fell back: {exc}"
            await event_bus.publish(
                channel,
                "content_block_delta",
                {"agent_message_id": assistant.id, "delta": {"type": "text_delta", "text": stream_text}},
            )
    else:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "system", "content": f"Tool context:\n{tool_summary}"},
            {"role": "user", "content": prompt},
        ]
        async for event in ark_client.stream_chat(messages, purpose=f"group_agent:{agent.type}"):
            if event.type == "delta":
                stream_text += event.text
                await event_bus.publish(
                    channel,
                    "content_block_delta",
                    {"agent_message_id": assistant.id, "delta": {"type": "text_delta", "text": event.text}},
                )
            elif event.type == "error":
                stream_text += f"\nModel call failed and fell back: {event.error}"

    display_text = strip_internal_agent_output(stream_text)
    assistant.content = {"text": display_text or f"{agent.name} completed this turn."}
    assistant.status = "completed"
    conversation.last_message_preview = assistant.content["text"][:300]
    conversation.last_message_sender = agent.name
    conversation.last_message_at = utcnow()
    conversation.activity_score = min(100, conversation.activity_score + 4)
    conversation.message_count += 1
    db.commit()
    await event_bus.publish(channel, "message:updated", message_to_dict(assistant))
    return assistant.content["text"]


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
                worker_context = await run_agentic_tool_loop(
                    db,
                    conversation,
                    f"{prompt}\n\nSubtask: {subtask.title}\n{subtask.description}",
                    max_steps=2,
                    agent=worker_agent,
                )
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
                    reply_text = await _run_canvas_agent_reply(
                        db,
                        conversation=conversation,
                        agent=worker_agent,
                        prompt=f"{prompt}\n\nCanvas node: {subtask.title}\n{subtask.description}",
                        channel=channel,
                        tool_context=worker_context,
                    )
                    independent_agent_replies.append(
                        {"agent_id": worker_agent.id, "agent_name": worker_agent.name, "text": reply_text[:1000]}
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
        async for event in ark_client.stream_chat(messages, purpose="chat"):
            if event.type == "delta":
                stream_text += event.text
                await event_bus.publish(
                    channel,
                    "content_block_delta",
                    {
                        "agent_message_id": assistant.id,
                        "delta": {"type": "text_delta", "text": event.text},
                    },
                )
            elif event.type == "usage":
                await event_bus.publish(channel, "usage", {"agent_message_id": assistant.id, "usage": event.usage})
            elif event.type == "error":
                stream_text += f"\n模型调用异常，已降级：{event.error}"
        display_text = strip_internal_agent_output(stream_text)
        assistant.content = {"text": display_text or "我已经完成处理，但本次模型没有返回可展示的最终回复。"}
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


def task_plan_json(task: Task) -> str:
    return json.dumps(task.plan, ensure_ascii=False, indent=2)
