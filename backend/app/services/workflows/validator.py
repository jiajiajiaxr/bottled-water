from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.models import Agent
from app.services.workflows.graph import WorkflowGraph

NODE_TYPES = {
    "start",
    "agent",
    "tool",
    "skill",
    "mcp",
    "condition",
    "loop",
    "review",
    "artifact",
    "end",
}
EXECUTABLE_NODE_TYPES = NODE_TYPES - {"start", "end"}


@dataclass
class WorkflowValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def format_workflow_validation_message(result: WorkflowValidationResult) -> str:
    details = "\n".join(f"- {item}" for item in result.errors)
    return f"当前工作流配置不完整，请先修复画布：\n{details}"


def _has_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _reachable_from_start(graph: WorkflowGraph, start_ids: list[str]) -> set[str]:
    reachable: set[str] = set()
    queue = list(start_ids)
    while queue:
        node_id = queue.pop(0)
        if node_id in reachable:
            continue
        reachable.add(node_id)
        queue.extend(edge.target for edge in graph.outgoing.get(node_id, []))
    return reachable


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
    start_nodes = [node for node in graph.nodes if node.type == "start"]
    end_nodes = [node for node in graph.nodes if node.type == "end"]
    executable_nodes = [node for node in graph.nodes if node.type in EXECUTABLE_NODE_TYPES]
    if not start_nodes:
        errors.append("workflow must contain a Start node")
    if not end_nodes:
        errors.append("workflow must contain an End node")
    if not executable_nodes:
        errors.append("workflow must contain at least one executable node")

    for node in graph.nodes:
        if node.type not in NODE_TYPES:
            errors.append(f"node {node.id} has unsupported type {node.type}")
        if node.type in {"agent", "review"} and not node.agent_id:
            errors.append(f"node {node.id} must select an agent")
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
        if node.type == "tool" and not _has_text(node.config.get("tool_name")):
            errors.append(f"tool node {node.id} must define tool_name")
        if node.type == "skill" and not _has_text(node.config.get("skill_id")):
            errors.append(f"skill node {node.id} must define skill_id")
        if node.type == "mcp" and not (
            _has_text(node.config.get("server_id")) and _has_text(node.config.get("tool_name"))
        ):
            errors.append(f"mcp node {node.id} must define server_id and tool_name")

    node_ids = set(graph.node_by_id)
    for edge in graph.edges:
        if edge.source not in node_ids or edge.target not in node_ids:
            errors.append(f"edge {edge.source}->{edge.target} references missing node")

    if graph.has_cycle():
        errors.append("workflow graph contains a cycle")
    if start_nodes:
        reachable = _reachable_from_start(graph, [node.id for node in start_nodes])
        for node in graph.nodes:
            if node.type != "start" and node.id not in reachable:
                errors.append(f"node {node.id} is not reachable from Start")
        for node in end_nodes:
            if node.id not in reachable:
                errors.append(f"End node {node.id} is not reachable")
    return WorkflowValidationResult(ok=not errors, errors=errors, warnings=warnings)
