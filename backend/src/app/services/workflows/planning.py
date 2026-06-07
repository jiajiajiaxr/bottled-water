from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy.orm import Session

from app.models import Agent, Conversation, utcnow
from app.services.llm.ark import ArkProviderError, ark_client
from app.services.realtime.event_bus import event_bus
from app.services.workflows.definition import WORKFLOW_REPLAN_PATTERN, _sanitize_workflow


def _select_agent(agents: list[Agent], capability: str) -> Agent | None:
    needle = capability.lower()
    for agent in agents:
        labels: list[str] = [str(agent.name or ""), str(agent.type or "")]
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
    match = re.search(r"\{.*\}", text or "", flags=re.S)
    if not match:
        return None
    try:
        value = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _normalize_plan(raw: dict[str, Any], fallback: dict[str, Any], agents: list[Agent]) -> dict[str, Any]:
    agent_ids = {str(agent.id) for agent in agents}
    subtasks: list[dict[str, Any]] = []
    raw_subtasks = raw.get("subtasks") if isinstance(raw.get("subtasks"), list) else []
    for index, item in enumerate(raw_subtasks[:4]):
        if not isinstance(item, dict):
            continue
        domain = str(item.get("domain") or item.get("category") or "general")
        try:
            priority = int(item.get("priority") or index + 1)
        except (TypeError, ValueError):
            priority = index + 1
        assigned = str(item.get("assigned_agent_id") or "")
        if assigned not in agent_ids:
            selected = _select_agent(agents, domain) or _select_agent(agents, str(item.get("title") or ""))
            assigned = str(selected.id) if selected else ""
        subtasks.append(
            {
                "subtask_id": str(item.get("subtask_id") or item.get("id") or f"st_{index + 1}"),
                "title": str(item.get("title") or f"Subtask {index + 1}")[:160],
                "description": str(item.get("description") or item.get("goal") or "")[:1200],
                "domain": domain,
                "priority": priority,
                "dependencies": [str(dep) for dep in item.get("dependencies") or []],
                "output_spec": str(item.get("output_spec") or item.get("deliverable") or "structured result"),
                "assigned_agent_id": assigned or None,
            }
        )
    if not subtasks:
        return fallback
    raw_edges = raw.get("dag_edges") if isinstance(raw.get("dag_edges"), list) else []
    edges = [
        [str(edge[0]), str(edge[1])]
        for edge in raw_edges
        if isinstance(edge, list) and len(edge) == 2
    ]
    return {
        "plan_id": str(raw.get("plan_id") or fallback["plan_id"]),
        "user_requirement": str(raw.get("user_requirement") or fallback["user_requirement"]),
        "complexity": str(raw.get("complexity") or fallback["complexity"]),
        "subtasks": subtasks,
        "dag_edges": edges or fallback.get("dag_edges", []),
        "planner": "ark",
    }


def build_plan(prompt: str, agents: list[Agent]) -> dict[str, Any]:
    frontend = _select_agent(agents, "frontend") or _select_agent(agents, "front")
    backend = _select_agent(agents, "backend") or _select_agent(agents, "api")
    reviewer = _select_agent(agents, "review") or _select_agent(agents, "test")
    fallback_agent = agents[0] if agents else None
    frontend = frontend or fallback_agent
    backend = backend or fallback_agent
    reviewer = reviewer or fallback_agent
    return {
        "plan_id": f"plan_{utcnow().strftime('%Y%m%d%H%M%S')}",
        "user_requirement": prompt,
        "complexity": "complex",
        "subtasks": [
            {
                "subtask_id": "st_frontend",
                "title": "Frontend workbench and preview",
                "description": "Implement the user-facing workbench, streaming message display, and preview surface.",
                "domain": "frontend",
                "priority": 1,
                "dependencies": [],
                "output_spec": "Interactive UI or previewable artifact",
                "assigned_agent_id": str(frontend.id) if frontend else None,
            },
            {
                "subtask_id": "st_backend",
                "title": "Backend API and runtime integration",
                "description": "Implement APIs, persistence, realtime events, and tool/runtime integration.",
                "domain": "backend",
                "priority": 1,
                "dependencies": [],
                "output_spec": "Working backend behavior and event stream",
                "assigned_agent_id": str(backend.id) if backend else None,
            },
            {
                "subtask_id": "st_review",
                "title": "Review and integration check",
                "description": "Review outputs and produce a concise final integration summary.",
                "domain": "review",
                "priority": 2,
                "dependencies": ["st_frontend", "st_backend"],
                "output_spec": "Review report and final summary",
                "assigned_agent_id": str(reviewer.id) if reviewer else None,
            },
        ],
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
        result = await ark_client.complete_stream_chat(
            [
                {
                    "role": "system",
                    "content": (
                        "You are an AgentHub task planner. Return JSON only with "
                        "plan_id, user_requirement, complexity, subtasks, dag_edges. "
                        "Each subtask must include subtask_id, title, description, domain, "
                        "priority, dependencies, output_spec, assigned_agent_id."
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
    planner = _select_agent(agents, "master") or _select_agent(agents, "plan") or (agents[0] if agents else None)
    if not planner:
        return workflow
    try:
        result = await ark_client.complete_stream_chat(
            [
                {
                    "role": "system",
                    "content": (
                        "You are an AgentHub workflow planning agent. Return JSON only. "
                        "Allowed node types: start, agent, tool, skill, mcp, condition, loop, review, artifact, end. "
                        "Preserve type/config fields and use only provided agent ids."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "instruction": prompt,
                            "current_workflow": workflow,
                            "agents": [
                                {
                                    "id": agent.id,
                                    "name": agent.name,
                                    "type": agent.type,
                                    "capabilities": agent.capabilities,
                                }
                                for agent in agents
                            ],
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
    except ArkProviderError:
        return workflow
