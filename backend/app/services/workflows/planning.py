from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy.orm import Session

from app.models import Agent, Conversation, utcnow
from app.services.ark import ArkProviderError, ark_client
from app.services.realtime.event_bus import event_bus
from app.services.workflows.definition import WORKFLOW_REPLAN_PATTERN, _sanitize_workflow


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
