from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Node:
    id: str
    type: str
    title: str
    role: str = ""
    config: dict[str, Any] = field(default_factory=dict)
    agent_id: str | None = None
    meta: str = ""

    @classmethod
    def from_dict(cls, value: dict[str, Any], index: int = 0) -> "Node":
        config = dict(value.get("config") if isinstance(value.get("config"), dict) else {})
        agent_id = value.get("agent_id") or config.get("agent_id")
        return cls(
            id=str(value.get("id") or f"node-{index + 1}"),
            type=str(value.get("type") or value.get("role") or "agent").lower(),
            title=str(value.get("title") or value.get("name") or f"Node {index + 1}"),
            role=str(value.get("role") or value.get("type") or "agent"),
            config=config,
            agent_id=str(agent_id) if agent_id else None,
            meta=str(value.get("meta") or value.get("description") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "type": self.type,
            "role": self.role,
            "config": self.config,
            "meta": self.meta,
            **({"agent_id": self.agent_id} if self.agent_id else {}),
        }


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    condition: str | None = None
    config: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_value(cls, value: Any) -> "Edge | None":
        if isinstance(value, list) and len(value) == 2:
            return cls(source=str(value[0]), target=str(value[1]))
        if not isinstance(value, dict):
            return None
        source = value.get("source") or value.get("from")
        target = value.get("target") or value.get("to")
        if not source or not target:
            return None
        config = dict(value.get("config") if isinstance(value.get("config"), dict) else {})
        condition = value.get("condition") or config.get("condition") or config.get("branch")
        return cls(source=str(source), target=str(target), condition=str(condition) if condition else None, config=config)

    def to_state(self) -> dict[str, Any]:
        return {
            "from": self.source,
            "to": self.target,
            "condition": self.condition,
            "status": "waiting",
            "config": self.config,
        }


class WorkflowGraph:
    def __init__(self, nodes: list[Node], edges: list[Edge]) -> None:
        self.nodes = nodes
        self.edges = edges
        self.node_by_id = {node.id: node for node in nodes}
        self.outgoing: dict[str, list[Edge]] = {node.id: [] for node in nodes}
        self.incoming: dict[str, list[Edge]] = {node.id: [] for node in nodes}
        for edge in edges:
            if edge.source in self.node_by_id and edge.target in self.node_by_id:
                self.outgoing[edge.source].append(edge)
                self.incoming[edge.target].append(edge)

    @classmethod
    def from_workflow(cls, workflow: dict[str, Any]) -> "WorkflowGraph":
        raw_nodes = workflow.get("nodes") if isinstance(workflow.get("nodes"), list) else []
        nodes = [Node.from_dict(item, index) for index, item in enumerate(raw_nodes) if isinstance(item, dict)]
        raw_edges = workflow.get("edges") if isinstance(workflow.get("edges"), list) else []
        edges = [edge for item in raw_edges if (edge := Edge.from_value(item))]
        return cls(nodes, edges)

    def topological_sort(self) -> list[Node]:
        ordered_ids = self._topological_ids()
        if len(ordered_ids) != len(self.nodes):
            return self.nodes
        return [self.node_by_id[node_id] for node_id in ordered_ids]

    def has_cycle(self) -> bool:
        return len(self._topological_ids()) != len(self.nodes)

    def _topological_ids(self) -> list[str]:
        indegree = {node.id: len(self.incoming.get(node.id, [])) for node in self.nodes}
        ready = [node.id for node in self.nodes if indegree[node.id] == 0]
        ordered: list[str] = []
        while ready:
            node_id = ready.pop(0)
            ordered.append(node_id)
            for edge in self.outgoing.get(node_id, []):
                indegree[edge.target] -= 1
                if indegree[edge.target] == 0:
                    ready.append(edge.target)
        return ordered

    def topological_levels(self) -> list[list[Node]]:
        indegree = {node.id: len(self.incoming.get(node.id, [])) for node in self.nodes}
        current = [node.id for node in self.nodes if indegree[node.id] == 0]
        levels: list[list[Node]] = []
        seen: set[str] = set()
        while current:
            levels.append([self.node_by_id[node_id] for node_id in current])
            seen.update(current)
            next_level: list[str] = []
            for node_id in current:
                for edge in self.outgoing.get(node_id, []):
                    indegree[edge.target] -= 1
                    if indegree[edge.target] == 0:
                        next_level.append(edge.target)
            current = next_level
        if len(seen) != len(self.nodes):
            return [[node] for node in self.nodes]
        return levels

    def branch_targets(self, node_id: str, branch: str | None) -> set[str]:
        edges = self.outgoing.get(node_id, [])
        if not branch:
            return {edge.target for edge in edges}
        matched = {edge.target for edge in edges if edge.condition in {branch, None, ""}}
        return matched or {edge.target for edge in edges}

    def skipped_targets_for_branch(self, node_id: str, branch: str | None) -> set[str]:
        targets = {edge.target for edge in self.outgoing.get(node_id, [])}
        return targets - self.branch_targets(node_id, branch)
