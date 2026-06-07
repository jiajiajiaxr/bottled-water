from __future__ import annotations

import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Agent, Conversation, ConversationParticipant, utcnow
from app.services.workflows.graph import Edge, WorkflowGraph
from app.services.workflows.runtime import build_node_states


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
    node_id = str(node.get("id") or "").lower().strip()
    title = str(node.get("title") or node.get("name") or "").lower().strip()
    role = str(node.get("role") or "").lower().strip()
    if node_id == "start" or title == "start" or role in {"input", "start"}:
        return "start"
    if node_id == "end" or title == "end" or role == "end":
        return "end"
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
        "output_mode": "independent_messages",
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
        position = node.get("position") or config.get("position")
        if (
            isinstance(position, dict)
            and isinstance(position.get("x"), (int, float))
            and isinstance(position.get("y"), (int, float))
        ):
            nodes[-1]["position"] = {"x": float(position["x"]), "y": float(position["y"])}
        if isinstance(node.get("data"), dict):
            nodes[-1]["data"] = node["data"]
    node_ids = {node["id"] for node in nodes}
    has_explicit_edges = isinstance(source.get("edges"), list)
    raw_edges = source.get("edges") if has_explicit_edges else fallback["edges"]
    edges: list[list[str] | dict[str, Any]] = []
    for raw_edge in raw_edges[:80]:
        edge = Edge.from_value(raw_edge)
        if not edge or edge.source not in node_ids or edge.target not in node_ids:
            continue
        if edge.condition or edge.config:
            edges.append(
                {
                    "from": edge.source,
                    "to": edge.target,
                    **({"condition": edge.condition} if edge.condition else {}),
                    **({"config": edge.config} if edge.config else {}),
                }
            )
        else:
            edges.append([edge.source, edge.target])
    return {
        **fallback,
        **{key: source[key] for key in ("mode", "output_mode", "settings") if key in source},
        "conversation_id": conversation.id,
        "nodes": nodes or fallback["nodes"],
        "edges": edges if has_explicit_edges else fallback["edges"],
    }


def _workflow_for_conversation(conversation: Conversation, agents: list[Agent]) -> dict[str, Any]:
    extra = conversation.extra or {}
    return _sanitize_workflow(conversation, agents, extra.get("workflow") if isinstance(extra.get("workflow"), dict) else None)


def _workflow_execution_order(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = [node for node in workflow.get("nodes", []) if isinstance(node, dict)]
    node_by_id = {str(node.get("id")): node for node in nodes}
    ordered = WorkflowGraph.from_workflow(workflow).topological_sort()
    if not ordered:
        return nodes
    return [node_by_id[node.id] for node in ordered if node.id in node_by_id]


def _workflow_node_states(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    return build_node_states(workflow)


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
