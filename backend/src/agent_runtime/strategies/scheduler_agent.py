"""Event-driven Team Leader scheduler actor."""

from __future__ import annotations

import asyncio
from typing import Any

from model_provider.core.interfaces import BaseModelProvider

from common.logger import get_logger
from ..context.blackboard import BlackboardManager
from ..core.protocol import (
    AGENT_FAILED,
    AGENT_REPORT,
    BLACKBOARD_UPDATED,
    CONTROL_ASSIGN,
    CONTROL_COMPLETE,
    CONTROL_PAUSE,
    CONTROL_RESUME,
    SCHEDULER_DECISION,
    USER_INPUT,
)
from ..core.types import AgentConfig, AgentReport, AgentState, AgentWill, Event, SchedulingDecision
from ..runtime.agent_actor import AgentActor
from ..runtime.event_dispatcher import EventDispatcher
from .tech_lead import TechLeadScheduler

logger = get_logger(__name__)

TEAM_LEADER_RUNTIME_PROMPT = """你是 AgentHub 群聊中的 Team Leader Agent。
你的职责是根据用户输入、Blackboard、各 Agent 状态报告，选择下一步调度动作：
assign、parallel、pause、wait 或 complete。你不是隐藏最高权限，只是擅长规划与协调的普通 Agent。"""


class SchedulerAgent(AgentActor):
    """A scheduler that behaves like an event-driven runtime actor."""

    def __init__(
        self,
        *,
        session_id: str,
        agents: dict[str, AgentConfig],
        event_bus: EventDispatcher,
        blackboard_mgr: BlackboardManager,
        model_provider: BaseModelProvider | None = None,
        scheduler_id: str = "team_leader",
    ) -> None:
        scheduler_config = AgentConfig(
            id=scheduler_id,
            name="Team Leader Scheduler",
            system_prompt=TEAM_LEADER_RUNTIME_PROMPT,
            role="leader",
        )
        super().__init__(
            session_id=session_id,
            agent_config=scheduler_config,
            model_provider=model_provider,  # SchedulerAgent overrides run(); AgentLoop is not invoked here.
            event_bus=event_bus,
            blackboard_mgr=blackboard_mgr,
            use_streaming=False,
        )
        self.agents = agents
        self.scheduler_id = scheduler_id
        self.reports: dict[str, AgentReport] = {}
        self.current_task = ""
        self.round_num = 0
        self._subscriptions: list[str] = []
        self._scheduler = TechLeadScheduler(agents=agents, model_provider=model_provider)
        self._mention_target_ids: list[str] = []
        self._bind()

    def _bind(self) -> None:
        for event_type in (USER_INPUT, AGENT_REPORT, BLACKBOARD_UPDATED, AGENT_FAILED):
            self._subscriptions.append(self.event_bus.subscribe(event_type, self.mailbox.send, target=None))

    def start(self) -> asyncio.Task:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self.run(), name=f"scheduler-agent:{self.session_id}")
        return self._task

    async def stop(self) -> None:
        self._closed = True
        await self.mailbox.send(
            Event(type=CONTROL_COMPLETE, payload={"reason": "scheduler_stop"}, source="system")
        )
        if self._task:
            await asyncio.wait([self._task], timeout=2)
        for subscription_id in self._subscriptions:
            self.event_bus.unsubscribe(subscription_id)
        self._subscriptions.clear()
        self.mailbox.close()

    async def run(self) -> None:
        await self._set_state(AgentState.READY, reason="scheduler_started")
        while not self._closed:
            event = await self.mailbox.recv()
            if event.type == CONTROL_COMPLETE:
                break
            should_schedule = await self._consume_event(event)
            if should_schedule:
                await self._schedule()
        await self._set_state(AgentState.COMPLETED, reason="scheduler_stopped")

    async def _consume_event(self, event: Event) -> bool:
        if event.type == USER_INPUT:
            self.current_task = str(event.payload.get("content") or event.payload.get("task") or "")
            self.reports = self._initial_reports()
            self._mention_target_ids = [
                str(item)
                for item in (event.payload.get("mention_target_agent_ids") or [])
                if str(item) in self.agents
            ]
            return bool(self.current_task)
        if event.type == AGENT_REPORT:
            report = _report_from_payload(event.payload.get("report") or {}, event.payload.get("agent_id"))
            self.reports[report.agent_id] = report
            return self.current_task and report.state in {AgentState.COMPLETED, AgentState.FAILED, AgentState.WAITING}
        if event.type == BLACKBOARD_UPDATED:
            return False
        if event.type == AGENT_FAILED:
            agent_id = str(event.payload.get("agent_id") or "")
            if agent_id:
                self.reports[agent_id] = AgentReport(
                    agent_id=agent_id,
                    state=AgentState.FAILED,
                    will=AgentWill.BLOCKED,
                    blockers=[str(event.payload.get("error") or "Agent failed")],
                    rationale="Agent failed; scheduler will re-plan.",
                    confidence=0.0,
                )
            return bool(self.current_task)
        return False

    async def _schedule(self) -> None:
        self.round_num += 1
        await self._set_state(AgentState.RUNNING, reason="scheduler_deciding")
        blackboard = await self.blackboard_mgr.get(self.session_id) or {}
        reports = list(self.reports.values()) or list(self._initial_reports().values())
        try:
            decision = self._mention_decision()
            if decision is None:
                decision = await self._scheduler.make_decision(
                    blackboard,
                    reports,
                    {
                        "round": self.round_num,
                        "session_id": self.session_id,
                        "current_task": self.current_task,
                        "agent_count": len(self.agents),
                    },
                )
                decision = self._normalize_decision(decision)
        except Exception as exc:
            logger.warning("SchedulerAgent fallback after decision failure", error=str(exc))
            decision = self._fallback_decision(reports)
            decision.fallback_reason = str(exc)[:500]

        await self._archive_decision(decision)
        await self.event_bus.publish(
            Event(
                type=SCHEDULER_DECISION,
                payload={"round": self.round_num, "decision": _decision_payload(decision)},
                source=f"scheduler:{self.scheduler_id}",
                channel="all",
            )
        )
        await self._publish_control(decision)
        if not self._closed:
            await self._set_state(AgentState.WAITING, reason="scheduler_waiting_for_reports")

    async def _publish_control(self, decision: SchedulingDecision) -> None:
        if decision.decision_type == "complete":
            await self.event_bus.publish(
                Event(
                    type=CONTROL_COMPLETE,
                    payload={"reason": decision.rationale, "round": self.round_num},
                    source=f"scheduler:{self.scheduler_id}",
                    channel="all",
                )
            )
            self._closed = True
            return

        if decision.decision_type == "wait":
            return

        if decision.decision_type == "resume" and decision.target_agent_id:
            await self.event_bus.publish(
                Event(
                    type=CONTROL_RESUME,
                    payload={"round": self.round_num, "rationale": decision.rationale},
                    source=f"scheduler:{self.scheduler_id}",
                    target=decision.target_agent_id,
                    channel="internal",
                )
            )
            return

        if decision.decision_type == "parallel":
            targets = decision.target_agent_ids or decision.verification_agents or [
                agent_id for agent_id, report in self.reports.items() if report.state in {AgentState.READY, AgentState.IDLE}
            ]
            if decision.target_agent_id:
                targets.insert(0, decision.target_agent_id)
            for target in dict.fromkeys(targets):
                if target in self.agents and target != self.scheduler_id:
                    await self._assign(target, decision)
            return

        if decision.decision_type == "pause" and decision.target_agent_id:
            await self.event_bus.publish(
                Event(
                    type=CONTROL_PAUSE,
                    payload={"round": self.round_num, "rationale": decision.rationale},
                    source=f"scheduler:{self.scheduler_id}",
                    target=decision.target_agent_id,
                    channel="internal",
                )
            )
            return

        if decision.target_agent_id:
            if decision.target_agent_id in self.agents and decision.target_agent_id != self.scheduler_id:
                await self._assign(decision.target_agent_id, decision)

    async def _assign(self, target: str, decision: SchedulingDecision) -> None:
        await self.event_bus.publish(
            Event(
                type=CONTROL_ASSIGN,
                payload={
                    "round": self.round_num,
                    "task": decision.task_description or self.current_task,
                    "rationale": decision.rationale,
                    "requires_verification": decision.requires_verification,
                },
                source=f"scheduler:{self.scheduler_id}",
                target=target,
                channel="internal",
            )
        )

    async def _archive_decision(self, decision: SchedulingDecision) -> None:
        await self.blackboard_mgr.append_history(
            self.session_id,
            {
                "type": "scheduler_agent_decision",
                "round": self.round_num,
                "decision": _decision_payload(decision),
            },
        )

    def _mention_decision(self) -> SchedulingDecision | None:
        targets = [
            agent_id
            for agent_id in dict.fromkeys(self._mention_target_ids)
            if agent_id in self.agents and agent_id != self.scheduler_id
        ]
        if not targets:
            return None
        return SchedulingDecision(
            decision_type="parallel" if len(targets) > 1 else "assign",
            action="assign",
            target_agent_id=targets[0],
            target_agent_ids=targets,
            task=self.current_task,
            task_description=self.current_task,
            rationale="用户 @ 指定了目标 Agent，本轮只调度被指定成员。",
            expected_outputs=["目标 Agent 的直接回复"],
        )

    def _normalize_decision(self, decision: SchedulingDecision) -> SchedulingDecision:
        if not decision.action:
            decision.action = "assign" if decision.decision_type == "parallel" else decision.decision_type
        if not decision.target_agent_ids:
            targets: list[str] = []
            if decision.target_agent_id:
                targets.append(decision.target_agent_id)
            targets.extend(decision.verification_agents or [])
            decision.target_agent_ids = [
                agent_id
                for agent_id in dict.fromkeys(targets)
                if agent_id in self.agents and agent_id != self.scheduler_id
            ]
        if not decision.task:
            decision.task = decision.task_description or self.current_task
        if not decision.task_description:
            decision.task_description = decision.task or self.current_task
        decision.requires_review = bool(decision.requires_review or decision.requires_verification)
        if not decision.expected_outputs:
            decision.expected_outputs = ["Agent 可见成果", "Blackboard 运行记录"]
        return decision

    def _initial_reports(self) -> dict[str, AgentReport]:
        return {
            agent_id: AgentReport(agent_id=agent_id, state=AgentState.READY, will=AgentWill.EXECUTE)
            for agent_id in self.agents
            if agent_id != self.scheduler_id
        }

    @staticmethod
    def _fallback_decision(reports: list[AgentReport]) -> SchedulingDecision:
        for report in reports:
            if report.state in {AgentState.READY, AgentState.IDLE}:
                return SchedulingDecision(
                    decision_type="assign",
                    target_agent_id=report.agent_id,
                    target_agent_ids=[report.agent_id],
                    action="assign",
                    task_description="继续处理当前用户任务",
                    rationale="SchedulerAgent rule fallback selected the first ready Agent.",
                    fallback_reason="rule_fallback",
                )
        if reports and all(report.state == AgentState.COMPLETED for report in reports):
            return SchedulingDecision(decision_type="complete", rationale="All Agents completed.")
        return SchedulingDecision(decision_type="wait", rationale="No ready Agent is available.")


def _report_from_payload(payload: dict[str, Any], fallback_agent_id: str | None) -> AgentReport:
    agent_id = str(payload.get("agent_id") or fallback_agent_id or "unknown")
    state = _state(payload.get("state"))
    will = _will(payload.get("will"))
    return AgentReport(
        agent_id=agent_id,
        state=state,
        will=will,
        target_task=payload.get("target_task"),
        blockers=list(payload.get("blockers") or []),
        priority=int(payload.get("priority") or 0),
        confidence=float(payload.get("confidence") or 0.0),
        rationale=str(payload.get("rationale") or ""),
        expected_duration=payload.get("expected_duration"),
    )


def _state(value: Any) -> AgentState:
    try:
        return AgentState(str(value))
    except ValueError:
        return AgentState.UNKNOWN


def _will(value: Any) -> AgentWill:
    try:
        return AgentWill(str(value))
    except ValueError:
        return AgentWill.WAIT


def _decision_payload(decision: SchedulingDecision) -> dict[str, Any]:
    return {
        "action": decision.action or ("assign" if decision.decision_type == "parallel" else decision.decision_type),
        "target_agent_ids": decision.target_agent_ids,
        "task": decision.task or decision.task_description,
        "expected_outputs": decision.expected_outputs,
        "requires_review": bool(decision.requires_review or decision.requires_verification),
        "fallback_reason": decision.fallback_reason,
        "decision_type": decision.decision_type,
        "target_agent_id": decision.target_agent_id,
        "task_description": decision.task_description,
        "rationale": decision.rationale,
        "requires_verification": decision.requires_verification,
        "verification_agents": decision.verification_agents,
    }
