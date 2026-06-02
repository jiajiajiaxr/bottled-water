"""
DAG Workflow 调度器

将旧 orchestrator 的 canvas-first DAG 执行模式封装为 Scheduler 接口，
作为第三种调度策略嵌入 agent_runtime。

注意：本模块属于 app 层，但只依赖纯 Python 和 agent_runtime 核心类型，
通过延迟导入避免循环依赖。
"""

from __future__ import annotations

import logging
import re
from typing import Any

from agent_runtime.core.types import AgentConfig, AgentReport, AgentWill, SchedulingDecision
from agent_runtime.strategies.base import Scheduler

logger = logging.getLogger(__name__)

WORKFLOW_NODE_TYPES = {"start", "agent", "tool", "skill", "mcp", "condition", "loop", "review", "artifact", "end"}
WORKFLOW_REPLAN_PATTERN = re.compile(
    r"(workflow|canvas|流程|画布|编排|规划|重排|调整工作流|让.*规划|master.*规划)", re.I
)


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


def _workflow_execution_order(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    """拓扑排序，返回 DAG 节点执行顺序"""
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


class WorkflowScheduler(Scheduler):
    """
    DAG Workflow 调度器。

    实现 Scheduler 接口，通过拓扑排序顺序返回 assign 决策，逐步执行 DAG 节点。
    上下文通过 set_workflow_context() 在每轮调度前注入。
    """

    def __init__(self, agents: dict[str, AgentConfig] | None = None):
        super().__init__(agents)
        self._round: int = 0
        self._workflow: dict[str, Any] = {}
        self._execution_order: list[dict[str, Any]] = []
        self._node_index: int = 0
        self._completed: bool = False
        self._prompt: str = ""

    def set_workflow_context(self, workflow: dict[str, Any], prompt: str) -> None:
        """设置 Workflow 执行上下文（在 make_decision 前调用）"""
        self._workflow = workflow
        self._prompt = prompt
        self._execution_order = _workflow_execution_order(workflow)
        self._node_index = 0
        self._completed = False
        self._round = 0

    async def make_decision(
        self,
        blackboard: dict[str, Any],
        agent_reports: list[AgentReport],
        conversation_context: dict[str, Any],
    ) -> SchedulingDecision:
        """基于 DAG 拓扑顺序返回下一个节点指派决策"""
        self._round += 1

        if self._completed:
            return SchedulingDecision(decision_type="complete", rationale="DAG 执行完毕")

        while self._node_index < len(self._execution_order):
            node = self._execution_order[self._node_index]
            node_type = _workflow_node_type(node)

            if node_type in {"start", "end", "condition", "loop", "tool", "skill", "mcp", "artifact"}:
                self._node_index += 1
                continue

            if node_type in {"agent", "review"}:
                self._node_index += 1
                agent_id = str(
                    node.get("agent_id")
                    or (node.get("config") or {}).get("agent_id")
                    or ""
                )
                return SchedulingDecision(
                    decision_type="assign",
                    target_agent_id=agent_id,
                    task_description=f"{self._prompt}\n\nNode: {node.get('title')}\n{node.get('meta') or ''}",
                    rationale=f"DAG node: {node.get('title')} ({node_type})",
                )

            self._node_index += 1
            continue

        self._completed = True
        return SchedulingDecision(decision_type="complete", rationale="DAG 所有节点执行完毕")

    async def resolve_conflict(
        self,
        conflict_type: str,
        conflicting_reports: list[AgentReport],
        blackboard: dict[str, Any],
    ) -> SchedulingDecision:
        return SchedulingDecision(
            decision_type="complete",
            rationale=f"Workflow 不处理冲突类型: {conflict_type}",
        )

    @property
    def workflow(self) -> dict[str, Any]:
        return self._workflow

    @property
    def execution_order(self) -> list[dict[str, Any]]:
        return self._execution_order

    @property
    def current_node_index(self) -> int:
        return self._node_index

    @property
    def is_completed(self) -> bool:
        return self._completed