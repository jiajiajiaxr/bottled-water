"""
单智能体调度器

纯代码驱动的调度器，用于单 Agent 场景。
无 LLM 调用，直接循环执行：请求用户输入 → 执行 → 产出结果 → 完成。
"""

from typing import Any

from ..core.types import AgentReport, SchedulingDecision
from .base import Scheduler


class SingleAgentScheduler(Scheduler):
    """单智能体调度器

    特性：
    - 纯代码逻辑，无 LLM 调用
    - 循环：assign → 执行 → 判断是否完成
    - 第一轮直接指派唯一 Agent，后续轮次判断完成状态
    """

    def __init__(self, agents: dict[str, Any] | None = None):
        super().__init__(agents)
        self._round: int = 0
        self._completed: bool = False
        self._first_agent_id: str | None = None

        if agents and len(agents) == 1:
            self._first_agent_id = next(iter(agents))

    @property
    def is_completed(self) -> bool:
        return self._completed

    def reset(self) -> None:
        """重置调度器状态。"""
        super().reset()
        self._round = 0
        self._completed = False

    async def make_decision(
        self,
        blackboard: dict[str, Any],
        agent_reports: list[AgentReport],
        conversation_context: dict[str, Any],
    ) -> SchedulingDecision:
        """单 Agent 调度决策"""
        self._round += 1

        if self._completed:
            return SchedulingDecision(
                decision_type="complete",
                rationale="任务已完成",
            )

        # 第一轮：指派唯一 Agent
        if self._round == 1:
            target = self._first_agent_id or (
                agent_reports[0].agent_id if agent_reports else None
            )
            task = conversation_context.get("current_task", "")
            return SchedulingDecision(
                decision_type="assign",
                target_agent_id=target or "",
                task_description=task,
                rationale="指派唯一 Agent 执行任务",
            )

        # 后续轮次：检查是否完成
        for report in agent_reports:
            if report.will.value in ("complete", "stop"):
                self._completed = True
                return SchedulingDecision(
                    decision_type="complete",
                    rationale=f"Agent {report.agent_id} 已完成",
                )

        # 还有任务在进行，继续
        active = [
            r for r in agent_reports if r.state not in ("completed", "failed")
        ]
        if not active:
            self._completed = True
            return SchedulingDecision(
                decision_type="complete",
                rationale="没有活跃的 Agent，任务结束",
            )

        # 仍在执行但没有新的调度需求，等待
        return SchedulingDecision(
            decision_type="wait",
            rationale="等待 Agent 执行完成",
        )

    async def resolve_conflict(
        self,
        conflict_type: str,
        conflicting_reports: list[AgentReport],
        blackboard: dict[str, Any],
    ) -> SchedulingDecision:
        """单 Agent 场景无冲突，直接完成"""
        return SchedulingDecision(
            decision_type="complete",
            rationale=f"单 Agent 场景不处理冲突类型: {conflict_type}",
        )