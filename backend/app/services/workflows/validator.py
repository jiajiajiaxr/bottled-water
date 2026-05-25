from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.models import Agent
from app.services.workflows.graph import WorkflowGraph

NODE_TYPES = {"start", "agent", "tool", "skill", "mcp", "condition", "loop", "review", "artifact", "end"}


@dataclass
class WorkflowValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def validate_workflow_graph(
    workflow: dict[str, Any],
    *,
    agents: list[Agent] | None = None,
    max_loop_iterations: int = 20,
) -> WorkflowValidationResult:
    graph = WorkflowGraph.from_workflow(workflow)
    errors: list[str] = []
    warnings: list[str] = []
    agent_ids = {agent.id for agent in agents or []}

    if not graph.nodes:
        errors.append("workflow must contain at least one node")
    for node in graph.nodes:
        if node.type not in NODE_TYPES:
            errors.append(f"node {node.id} has unsupported type {node.type}")
        if node.type in {"agent", "review"} and node.agent_id and agent_ids and node.agent_id not in agent_ids:
            errors.append(f"node {node.id} references unavailable agent {node.agent_id}")
        if node.type == "loop":
            try:
                iterations = int(node.config.get("max_iterations") or 1)
            except (TypeError, ValueError):
                errors.append(f"loop node {node.id} has invalid max_iterations")
                continue
            if iterations < 1 or iterations > max_loop_iterations:
                errors.append(f"loop node {node.id} max_iterations must be 1..{max_loop_iterations}")
        if node.type == "tool" and not node.config.get("tool_name"):
            warnings.append(f"tool node {node.id} has no tool_name")
        if node.type == "skill" and not node.config.get("skill_id"):
            warnings.append(f"skill node {node.id} has no skill_id")
        if node.type == "mcp" and not (node.config.get("server_id") and node.config.get("tool_name")):
            warnings.append(f"mcp node {node.id} should define server_id and tool_name")

    node_ids = set(graph.node_by_id)
    for edge in graph.edges:
        if edge.source not in node_ids or edge.target not in node_ids:
            errors.append(f"edge {edge.source}->{edge.target} references missing node")

    if graph.has_cycle():
        errors.append("workflow graph contains a cycle")
    return WorkflowValidationResult(ok=not errors, errors=errors, warnings=warnings)
