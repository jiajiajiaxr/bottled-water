"""Async Agent Actor runtime."""

from __future__ import annotations

import asyncio
from typing import Any

from model_provider.core.interfaces import BaseModelProvider

from common.logger import get_logger
from ..context.agent_ctx import AgentContextManager
from ..context.blackboard import BlackboardManager
from ..core.interfaces import ToolExecutor
from ..core.protocol import (
    AGENT_FAILED,
    AGENT_REPORT,
    AGENT_STATE_CHANGED,
    CONTROL_ASSIGN,
    CONTROL_CANCEL,
    CONTROL_COMPLETE,
    CONTROL_SHUTDOWN,
)
from ..core.types import AgentConfig, AgentReport, AgentState, AgentWill, Event
from .agent_loop import AgentLoop
from .agent_stepper import AgentStepper
from .event_dispatcher import EventDispatcher
from .mailbox import Mailbox

logger = get_logger(__name__)


class AgentActor:
    """Long-lived asyncio actor for one Agent."""

    def __init__(
        self,
        *,
        session_id: str,
        agent_config: AgentConfig,
        model_provider: BaseModelProvider,
        event_bus: EventDispatcher,
        tool_executor: ToolExecutor | None = None,
        blackboard_mgr: BlackboardManager | None = None,
        agent_context_mgr: AgentContextManager | None = None,
        use_streaming: bool = True,
    ) -> None:
        self.session_id = session_id
        self.config = agent_config
        self.event_bus = event_bus
        self.tool_executor = tool_executor
        self.blackboard_mgr = blackboard_mgr or BlackboardManager()
        self.agent_context_mgr = agent_context_mgr or AgentContextManager()
        self.mailbox = Mailbox(agent_config.id)
        self.mailbox.bind(event_bus, event_filter="control.*", target=agent_config.id)
        self.loop = AgentLoop(agent_config, model_provider, use_streaming=use_streaming)
        self.stepper = AgentStepper(self.loop, self.mailbox)
        self.state = AgentState.IDLE
        self._task: asyncio.Task | None = None
        self._closed = False

    def start(self) -> asyncio.Task:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self.run(), name=f"agent-actor:{self.config.id}")
        return self._task

    async def stop(self) -> None:
        self._closed = True
        await self.mailbox.send(
            Event(
                type=CONTROL_SHUTDOWN,
                payload={"reason": "actor_stop"},
                source="system",
                target=self.config.id,
                channel="internal",
            )
        )
        if self._task:
            await asyncio.wait([self._task], timeout=2)
        self.mailbox.close()

    async def run(self) -> None:
        await self._set_state(AgentState.READY, reason="actor_started")
        while not self._closed:
            event = await self.mailbox.recv()
            if event.type in {CONTROL_CANCEL, CONTROL_SHUTDOWN}:
                await self.stepper.apply_control(event)
                await self._set_state(AgentState.FAILED, reason=event.type)
                break
            if event.type == CONTROL_COMPLETE:
                await self.stepper.apply_control(event)
                report = self.stepper.terminal_report()
                await self._publish_report(report, work_product="", task=None)
                await self._set_state(AgentState.COMPLETED, reason=event.type)
                break
            if event.type != CONTROL_ASSIGN:
                await self.stepper.apply_control(event)
                await self._set_state(self.stepper.state, reason=event.type)
                continue

            task = event.payload.get("task") or event.payload.get("task_description") or ""
            if not task:
                await self._publish_report(
                    AgentReport(
                        agent_id=self.config.id,
                        state=AgentState.FAILED,
                        will=AgentWill.BLOCKED,
                        rationale="control.assign missing task",
                        confidence=1.0,
                    ),
                    work_product="",
                )
                continue
            await self._execute_assignment(str(task), event)

        final_state = AgentState.FAILED if self.stepper.cancel_requested else AgentState.COMPLETED
        await self._set_state(final_state, reason="actor_stopped")

    async def _execute_assignment(self, task: str, source_event: Event) -> None:
        await self._set_state(AgentState.RUNNING, reason="assignment_started", task=task)
        try:
            blackboard = await self.blackboard_mgr.get(self.session_id)
            if blackboard is None:
                blackboard = await self.blackboard_mgr.create(self.session_id)
            agent_ctx = self.agent_context_mgr.get(self.config.id, self.session_id)

            async def emit_event(event: Event) -> None:
                event.correlation_id = event.correlation_id or source_event.correlation_id
                await self.event_bus.publish(event)

            result = await self.stepper.run_assignment(
                task,
                blackboard,
                tool_executor=self.tool_executor,
                agent_ctx=agent_ctx,
                emit_event=emit_event,
            )
            output = result.output
            report = result.report
            work_product = str(output.get("work_product") or "")
            history_type = "agent_control" if result.interrupted else "agent_work"
            await self.blackboard_mgr.append_history(
                self.session_id,
                {
                    "type": history_type,
                    "agent_id": self.config.id,
                    "task": task,
                    "content": work_product,
                    "interrupted": result.interrupted,
                    "report": _report_payload(report),
                },
            )
            await self._publish_report(report, work_product=work_product, task=task)
            await self._set_state(report.state, reason="assignment_completed", task=task)
        except Exception as exc:
            logger.exception("AgentActor assignment failed", agent_id=self.config.id)
            report = AgentReport(
                agent_id=self.config.id,
                state=AgentState.FAILED,
                will=AgentWill.BLOCKED,
                blockers=[str(exc)],
                rationale=f"AgentActor failed: {type(exc).__name__}",
                confidence=0.0,
            )
            await self.blackboard_mgr.append_history(
                self.session_id,
                {
                    "type": "agent_error",
                    "agent_id": self.config.id,
                    "task": task,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
            )
            await self._publish_report(report, work_product="", task=task)
            await self.event_bus.publish(
                Event(
                    type=AGENT_FAILED,
                    payload={"agent_id": self.config.id, "error": str(exc), "task": task},
                    source=f"agent:{self.config.id}",
                    channel="all",
                )
            )
            await self._set_state(AgentState.FAILED, reason="assignment_failed", task=task)

    async def _publish_report(
        self,
        report: AgentReport,
        *,
        work_product: str,
        task: str | None = None,
    ) -> None:
        await self.event_bus.publish(
            Event(
                type=AGENT_REPORT,
                payload={
                    "agent_id": self.config.id,
                    "task": task,
                    "work_product": work_product,
                    "report": _report_payload(report),
                },
                source=f"agent:{self.config.id}",
                channel="all",
            )
        )

    async def _set_state(self, state: AgentState, *, reason: str, task: str | None = None) -> None:
        if self.state == state and reason != "assignment_started":
            return
        old_state = self.state
        self.state = state
        await self.event_bus.publish(
            Event(
                type=AGENT_STATE_CHANGED,
                payload={
                    "agent_id": self.config.id,
                    "agent_name": self.config.name,
                    "old_state": old_state.value,
                    "state": state.value,
                    "reason": reason,
                    "task": task,
                },
                source=f"agent:{self.config.id}",
                channel="all",
            )
        )


def _report_payload(report: AgentReport) -> dict[str, Any]:
    return {
        "agent_id": report.agent_id,
        "state": report.state.value,
        "will": report.will.value,
        "target_task": report.target_task,
        "blockers": report.blockers,
        "priority": report.priority,
        "confidence": report.confidence,
        "rationale": report.rationale,
        "expected_duration": report.expected_duration,
    }
