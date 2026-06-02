from __future__ import annotations

from dataclasses import dataclass, field

from app.services.workflows.graph import Node, WorkflowGraph


@dataclass
class WorkflowSchedule:
    levels: list[list[Node]]
    skipped: set[str] = field(default_factory=set)


class WorkflowScheduler:
    def __init__(self, graph: WorkflowGraph) -> None:
        self.graph = graph

    def serial(self) -> list[list[Node]]:
        return [[node] for node in self.graph.topological_sort()]

    def parallel_levels(self) -> list[list[Node]]:
        return self.graph.topological_levels()

    def skip_branch_targets(self, condition_node_id: str, matched_branch: str | None) -> set[str]:
        return self.graph.skipped_targets_for_branch(condition_node_id, matched_branch)
