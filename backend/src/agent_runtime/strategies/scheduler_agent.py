"""Event-driven Team Leader scheduler actor."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from collections.abc import Callable
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
    SCHEDULER_PLAN,
    SCHEDULER_SUMMARY,
    USER_INPUT,
)
from ..core.types import AgentConfig, AgentReport, AgentState, AgentWill, Event, SchedulingDecision
from ..runtime.agent_actor import AgentActor
from ..runtime.event_dispatcher import EventDispatcher
from .tech_lead import TechLeadScheduler

logger = get_logger(__name__)
SCHEDULER_DECISION_TIMEOUT_SECONDS = 12.0
MAX_PLAN_TASKS = 8
MAX_SUMMARY_ITEMS = 8

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
            model_provider=None,  # SchedulerAgent overrides run(); AgentLoop is not invoked here.
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
        self._mention_dispatched_ids: set[str] = set()
        self._assigned_agent_ids: set[str] = set()
        self._inflight_agent_ids: set[str] = set()
        self._context_metadata: dict[str, Any] = {}
        self._turn_plan: list[dict[str, Any]] = []
        self._agent_outputs: dict[str, dict[str, Any]] = {}
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
            mention_targets = list(event.payload.get("mention_target_agent_ids") or [])
            mention_targets.extend(_mention_target_ids_from_metadata(event.payload.get("context_metadata")))
            self._mention_target_ids = [
                str(item)
                for item in mention_targets
                if str(item) in self.agents
            ]
            self._mention_target_ids = list(dict.fromkeys(self._mention_target_ids))
            self._mention_dispatched_ids = set()
            self._assigned_agent_ids = set()
            self._inflight_agent_ids = set()
            self._agent_outputs = {}
            self._context_metadata = _dict_payload(event.payload.get("context_metadata"))
            self._turn_plan = self._build_turn_plan(self.current_task)
            await self._archive_plan()
            await self.event_bus.publish(
                Event(
                    type=SCHEDULER_PLAN,
                    payload={
                        "round": 0,
                        "task": self.current_task,
                        "plan": self._turn_plan,
                        "target_agent_ids": [
                            item["agent_id"]
                            for item in self._turn_plan
                            if item.get("agent_id")
                        ],
                    },
                    source=f"scheduler:{self.scheduler_id}",
                    channel="all",
                )
            )
            return bool(self.current_task)
        if event.type == AGENT_REPORT:
            report = _report_from_payload(event.payload.get("report") or {}, event.payload.get("agent_id"))
            if event.payload.get("work_product") and report.state in {
                AgentState.IDLE,
                AgentState.READY,
                AgentState.RUNNING,
                AgentState.WAITING,
                AgentState.UNKNOWN,
            }:
                report.state = AgentState.COMPLETED
                report.will = AgentWill.COMPLETE
            self.reports[report.agent_id] = report
            self._inflight_agent_ids.discard(report.agent_id)
            self._record_agent_output(event.payload, report)
            return self.current_task and report.state in {AgentState.COMPLETED, AgentState.FAILED, AgentState.WAITING}
        if event.type == BLACKBOARD_UPDATED:
            return False
        if event.type == AGENT_FAILED:
            agent_id = str(event.payload.get("agent_id") or "")
            if agent_id:
                self._inflight_agent_ids.discard(agent_id)
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
                decision = self._completion_decision_for_terminal_reports(reports)
            if decision is None:
                decision = self._greeting_decision(reports)
            if decision is None:
                decision = await asyncio.wait_for(
                    self._scheduler.make_decision(
                        blackboard,
                        reports,
                        {
                            "round": self.round_num,
                            "session_id": self.session_id,
                            "current_task": self.current_task,
                            "agent_count": len(self.agents),
                        },
                    ),
                    timeout=SCHEDULER_DECISION_TIMEOUT_SECONDS,
                )
        except Exception as exc:
            logger.warning("SchedulerAgent fallback after decision failure", error=str(exc))
            decision = self._fallback_decision(reports)
            decision.fallback_reason = str(exc)[:500]

        decision = self._normalize_decision(decision)
        decision = self._repair_decision(decision, reports)

        await self._archive_decision(decision)
        await self.event_bus.publish(
            Event(
                type=SCHEDULER_DECISION,
                payload={
                    "round": self.round_num,
                    "decision": _decision_payload(decision),
                    "plan": self._turn_plan,
                    "summary": self._runtime_summary(),
                },
                source=f"scheduler:{self.scheduler_id}",
                channel="all",
            )
        )
        await self._publish_control(decision)
        if not self._closed:
            await self._set_state(AgentState.WAITING, reason="scheduler_waiting_for_reports")

    async def _publish_control(self, decision: SchedulingDecision) -> None:
        mention_targets = set(self._valid_target_ids(self._mention_target_ids))

        if decision.decision_type == "complete":
            summary = self._runtime_summary()
            await self.blackboard_mgr.append_history(
                self.session_id,
                {"type": "scheduler_agent_summary", "round": self.round_num, **summary},
            )
            await self.event_bus.publish(
                Event(
                    type=SCHEDULER_SUMMARY,
                    payload={"round": self.round_num, **summary},
                    source=f"scheduler:{self.scheduler_id}",
                    channel="all",
                )
            )
            await self.event_bus.publish(
                Event(
                    type=CONTROL_COMPLETE,
                    payload={
                        "reason": decision.rationale,
                        "round": self.round_num,
                        "summary": summary,
                    },
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
            targets = list(decision.target_agent_ids or decision.verification_agents or [
                agent_id for agent_id, report in self.reports.items() if report.state in {AgentState.READY, AgentState.IDLE}
            ])
            if decision.target_agent_id:
                targets.insert(0, decision.target_agent_id)
            targets = list(dict.fromkeys(targets))
            if mention_targets:
                targets = [target for target in targets if target in mention_targets]
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
            if mention_targets and decision.target_agent_id not in mention_targets:
                return
            if decision.target_agent_id in self.agents and decision.target_agent_id != self.scheduler_id:
                await self._assign(decision.target_agent_id, decision)

    async def _assign(self, target: str, decision: SchedulingDecision) -> None:
        self._assigned_agent_ids.add(target)
        self._inflight_agent_ids.add(target)
        if target in self._mention_target_ids:
            self._mention_dispatched_ids.add(target)
        assigned_task = self._assignment_task_for_target(target, decision)
        await self.event_bus.publish(
            Event(
                type=CONTROL_ASSIGN,
                payload={
                    "round": self.round_num,
                    "task": assigned_task,
                    "task_input": {
                        "user_request": self.current_task,
                        "assigned_task": assigned_task,
                        "scheduler_task": decision.task_description or decision.task or self.current_task,
                        "plan": deepcopy(self._turn_plan),
                        "upstream_outputs": deepcopy(self._agent_outputs),
                    },
                    "rationale": decision.rationale,
                    "requires_verification": decision.requires_verification,
                    "context_metadata": self._context_metadata,
                },
                source=f"scheduler:{self.scheduler_id}",
                target=target,
                channel="internal",
            )
        )

    def _assignment_task_for_target(self, target: str, decision: SchedulingDecision) -> str:
        plan_item = self._plan_item_for_agent(target)
        plan_task = str(
            (plan_item or {}).get("assigned_task")
            or (plan_item or {}).get("task")
            or ""
        ).strip()
        if plan_task:
            return plan_task
        return str(decision.task_description or decision.task or self.current_task or "").strip()

    def _plan_item_for_agent(self, agent_id: str) -> dict[str, Any] | None:
        for item in self._turn_plan:
            if isinstance(item, dict) and str(item.get("agent_id") or "") == agent_id:
                return item
        return None

    async def _archive_decision(self, decision: SchedulingDecision) -> None:
        await self.blackboard_mgr.append_history(
            self.session_id,
            {
                "type": "scheduler_agent_decision",
                "round": self.round_num,
                "decision": _decision_payload(decision),
                "plan": self._turn_plan,
                "summary": self._runtime_summary(),
            },
        )

    async def _archive_plan(self) -> None:
        await self.blackboard_mgr.append_history(
            self.session_id,
            {
                "type": "scheduler_agent_plan",
                "task": self.current_task,
                "plan": self._turn_plan,
            },
        )

    def _build_turn_plan(self, task: str) -> list[dict[str, Any]]:
        mention_targets = self._valid_target_ids(self._mention_target_ids)
        named_targets = self._agent_ids_mentioned_in(task)
        if mention_targets:
            targets = mention_targets
        elif _is_simple_greeting_utf8(task):
            chat_agent_id = self._chat_agent_id()
            targets = [chat_agent_id] if chat_agent_id else self._schedulable_agent_ids()[:1]
        else:
            targets = self._select_targets_for_task(task, named_targets)
        plan: list[dict[str, Any]] = []
        for index, agent_id in enumerate(targets[:MAX_PLAN_TASKS], start=1):
            agent = self.agents.get(agent_id)
            if not agent:
                continue
            stage, depends_on = self._plan_stage_for_agent(agent_id, agent, targets)
            display_task = self._display_task_for_agent(task, agent_id, agent)
            assigned_task = self._task_for_agent(task, agent)
            plan.append(
                {
                    "id": f"auto-{index}",
                    "agent_id": agent_id,
                    "agent_name": agent.name,
                    "role": agent.role,
                    "priority": index,
                    "stage": stage,
                    "depends_on": depends_on,
                    "status": "queued",
                    "task": display_task,
                    "assigned_task": assigned_task,
                    "expected_outputs": self._expected_outputs_for_agent(agent),
                    "rationale": self._agent_fit_rationale(agent),
                }
            )
        return plan

    def _record_agent_output(self, payload: dict[str, Any], report: AgentReport) -> None:
        agent_id = report.agent_id or str(payload.get("agent_id") or "")
        if not agent_id:
            return
        work_product = str(payload.get("work_product") or "")
        task = str(payload.get("task") or "")
        tool_events = payload.get("tool_events") if isinstance(payload.get("tool_events"), list) else []
        self._agent_outputs[agent_id] = {
            "agent_id": agent_id,
            "task": task,
            "status": report.state.value,
            "will": report.will.value,
            "output": work_product,
            "structured_output": deepcopy(payload.get("output")) if isinstance(payload.get("output"), dict) else {},
            "output_preview": work_product[:500],
            "rationale": report.rationale,
            "confidence": report.confidence,
            "blockers": report.blockers,
            "tool_events": tool_events,
        }
        for item in self._turn_plan:
            if item.get("agent_id") != agent_id:
                continue
            item["status"] = report.state.value
            item["output_preview"] = work_product[:300]
            item["confidence"] = report.confidence
            item["blockers"] = report.blockers
            item["tool_events"] = tool_events
            break

    def _runtime_summary(self) -> dict[str, Any]:
        outputs = list(self._agent_outputs.values())[-MAX_SUMMARY_ITEMS:]
        completed = [item for item in outputs if item.get("status") == AgentState.COMPLETED.value]
        failed = [item for item in outputs if item.get("status") == AgentState.FAILED.value]
        waiting = [item for item in outputs if item.get("status") == AgentState.WAITING.value]
        pending = [
            item
            for item in self._turn_plan
            if item.get("agent_id") not in self._agent_outputs
        ]
        in_progress = [
            item
            for item in self._turn_plan
            if item.get("agent_id") in self._inflight_agent_ids
            and item.get("agent_id") not in self._agent_outputs
        ]
        status = "completed"
        if failed:
            status = "completed_with_failures" if completed else "failed"
        elif waiting or pending or in_progress:
            status = "partial"
        coordination_gaps = self._coordination_gaps(outputs)
        if status == "completed" and coordination_gaps:
            status = "completed_with_coordination_gaps"
        final_deliverable = self._build_final_deliverable(
            status=status,
            outputs=outputs,
            failed=failed,
            pending=pending,
            in_progress=in_progress,
            coordination_gaps=coordination_gaps,
        )
        return {
            "status": status,
            "task": self.current_task,
            "plan": self._turn_plan,
            "agent_outputs": outputs,
            "completed_agent_ids": [item["agent_id"] for item in completed],
            "failed_agent_ids": [item["agent_id"] for item in failed],
            "waiting_agent_ids": [item["agent_id"] for item in waiting],
            "pending_agent_ids": [str(item.get("agent_id")) for item in pending if item.get("agent_id")],
            "inflight_agent_ids": list(self._inflight_agent_ids),
            "coordination_gaps": coordination_gaps,
            "source_reviews": final_deliverable["source_reviews"],
            "logic_chain": final_deliverable["logic_chain"],
            "compliance_checks": final_deliverable["compliance_checks"],
            "final_product": final_deliverable["final_product"],
            "final_deliverable": final_deliverable,
            "publish_message": final_deliverable["publish_message"],
            "final_answer": self._compose_final_answer(final_deliverable),
        }

    def _coordination_gaps(self, outputs: list[dict[str, Any]]) -> list[str]:
        gaps: list[str] = []
        for output in outputs:
            agent_id = str(output.get("agent_id") or "")
            text = str(output.get("output") or output.get("output_preview") or "").lower()
            agent = self.agents.get(agent_id)
            label = agent.name if agent else agent_id or "Agent"
            if "review_quality=independent" in text:
                gaps.append(f"{label} did not consume upstream implementation outputs.")
            if "readiness_quality=generic" in text:
                gaps.append(f"{label} did not consume implementation and review outputs.")
        return gaps[:MAX_SUMMARY_ITEMS]

    def _build_final_deliverable(
        self,
        *,
        status: str,
        outputs: list[dict[str, Any]],
        failed: list[dict[str, Any]],
        pending: list[dict[str, Any]],
        in_progress: list[dict[str, Any]],
        coordination_gaps: list[str],
    ) -> dict[str, Any]:
        source_reviews = [self._source_review_for_output(output) for output in outputs[:MAX_SUMMARY_ITEMS]]
        logic_chain = self._final_logic_chain(outputs)
        compliance_checks = self._final_compliance_checks(
            outputs=outputs,
            failed=failed,
            pending=pending,
            in_progress=in_progress,
            coordination_gaps=coordination_gaps,
        )
        standardized_sections = [
            {
                "agent_id": review["agent_id"],
                "agent_name": review["agent_name"],
                "title": f"{review['agent_name']} 成果",
                "content": self._section_summary_for_review(review),
            }
            for review in source_reviews
            if review.get("output") or review.get("artifacts") or self._should_surface_empty_output(review)
        ]
        risks = [str(item) for item in coordination_gaps]
        risks.extend(
            f"{self._agent_label(str(item.get('agent_id') or 'Agent'))} 未完成或等待补充。"
            for item in [*failed, *pending, *in_progress]
            if item.get("agent_id")
        )
        if not risks:
            risks.append("当前未发现阻断项；后续可按交付内容进入人工验收或下一轮深化。")
        final_product = self._final_product(source_reviews)
        is_collaborative = len(source_reviews) > 1 or any(item.get("depends_on") for item in source_reviews)
        publish_message = bool(is_collaborative and self._should_publish_team_leader_message(source_reviews))
        return {
            "title": "Team Leader 最终交付",
            "status": status,
            "objective": self.current_task,
            "is_collaborative": is_collaborative,
            "publish_message": publish_message,
            "source_reviews": source_reviews,
            "logic_chain": logic_chain,
            "compliance_checks": compliance_checks,
            "final_product": final_product,
            "standardized_sections": standardized_sections,
            "risks": risks[:MAX_SUMMARY_ITEMS],
        }

    def _should_publish_team_leader_message(self, source_reviews: list[dict[str, Any]]) -> bool:
        if len(source_reviews) <= 1:
            return False
        if self._looks_like_complex_task(self.current_task):
            return True
        if any(review.get("artifacts") for review in source_reviews):
            return True
        return False

    def _source_review_for_output(self, output: dict[str, Any]) -> dict[str, Any]:
        agent_id = str(output.get("agent_id") or "")
        agent = self.agents.get(agent_id)
        plan_item = self._plan_item_for_agent(agent_id) or {}
        tool_events = output.get("tool_events") if isinstance(output.get("tool_events"), list) else []
        structured_output = output.get("structured_output") if isinstance(output.get("structured_output"), dict) else {}
        return {
            "agent_id": agent_id,
            "agent_name": self._agent_label(agent_id),
            "role": str(agent.role if agent else ""),
            "stage": plan_item.get("stage"),
            "depends_on": list(plan_item.get("depends_on") or []),
            "task": str(output.get("task") or plan_item.get("task") or ""),
            "status": str(output.get("status") or "unknown"),
            "confidence": output.get("confidence"),
            "rationale": str(output.get("rationale") or ""),
            "tool_count": sum(
                len(item.get("results") or [])
                for item in tool_events
                if isinstance(item, dict)
            ),
            "artifacts": [
                *self._artifacts_from_structured_output(structured_output),
                *self._artifacts_from_tool_events(tool_events),
            ][:MAX_SUMMARY_ITEMS],
            "structured_output": structured_output,
            "output": str(output.get("output") or output.get("output_preview") or "").strip(),
        }

    def _artifacts_from_structured_output(self, output: dict[str, Any]) -> list[dict[str, Any]]:
        candidates: list[Any] = []
        for key in ("artifact", "artifacts", "preview", "preview_card", "file", "files"):
            value = output.get(key)
            if isinstance(value, list):
                candidates.extend(value)
            elif isinstance(value, dict):
                candidates.append(value)
        if any(output.get(key) for key in ("artifact_id", "preview_message_id", "filename", "public_url")):
            candidates.append(output)
        artifacts: list[dict[str, Any]] = []
        for item in candidates:
            artifact = _artifact_reference(item)
            if artifact:
                artifacts.append(artifact)
        return artifacts[:MAX_SUMMARY_ITEMS]

    def _artifacts_from_tool_events(self, tool_events: list[Any]) -> list[dict[str, Any]]:
        artifacts: list[dict[str, Any]] = []
        for tool_event in tool_events:
            if not isinstance(tool_event, dict):
                continue
            for result in tool_event.get("results") or []:
                if not isinstance(result, dict):
                    continue
                candidates = _tool_result_candidates(result)
                artifact = next(
                    (candidate for candidate in (_artifact_reference(item) for item in candidates) if candidate),
                    {},
                )
                if artifact:
                    artifact["tool"] = result.get("tool") or result.get("tool_name") or tool_event.get("tool")
                    artifacts.append(artifact)
        return artifacts[:MAX_SUMMARY_ITEMS]

    def _final_product(self, source_reviews: list[dict[str, Any]]) -> dict[str, Any]:
        sections = [
            {
                "agent_id": item.get("agent_id"),
                "agent_name": item.get("agent_name"),
                "status": item.get("status"),
                "summary": self._section_summary_for_review(item),
                "content": self._section_summary_for_review(item),
                "artifacts": self._unique_artifacts(item.get("artifacts") or []),
            }
            for item in source_reviews
            if item.get("output") or item.get("artifacts") or self._should_surface_empty_output(item)
        ]
        primary = next((item for item in sections if str(item.get("content") or "").strip()), None)
        artifacts = self._unique_artifacts([
            artifact
            for item in sections
            for artifact in item.get("artifacts") or []
            if isinstance(artifact, dict)
        ])[:MAX_SUMMARY_ITEMS]
        if len(sections) == 1 and primary:
            single_review = source_reviews[0] if source_reviews else {}
            content = (
                str(single_review.get("output") or "").strip()
                or str(primary.get("content") or "").strip()
            )
        else:
            content = self._integrated_product_summary(source_reviews, sections, artifacts)
        return {
            "type": "single" if len(sections) <= 1 else "integrated",
            "content": content,
            "sections": sections,
            "artifacts": artifacts,
        }

    def _integrated_product_summary(
        self,
        source_reviews: list[dict[str, Any]],
        sections: list[dict[str, Any]],
        artifacts: list[dict[str, Any]],
    ) -> str:
        if not sections:
            return "本轮未形成可直接展示的最终成品。"
        objective = _clip_text(self.current_task, 96)
        completed = [
            item
            for item in source_reviews
            if str(item.get("status") or "").lower() == AgentState.COMPLETED.value
        ]
        capability_labels = [
            self._capability_label_for_review(item)
            for item in source_reviews
            if item.get("output") or item.get("artifacts")
        ]
        capability_text = "、".join(dict.fromkeys(capability_labels)) or "专项成果"
        artifact_text = (
            f"已关联 {len(artifacts)} 个可预览/可导出的产物卡片"
            if artifacts
            else "当前未检测到独立产物卡片，最终内容以内联交付为准"
        )
        objective_text = f"围绕「{objective}」，" if objective else ""
        return (
            f"{objective_text}已整合 {len(completed)}/{len(source_reviews)} 个子 Agent 的{capability_text}，"
            f"形成面向用户验收的标准化交付包；{artifact_text}。"
        )

    @staticmethod
    def _should_surface_empty_output(item: dict[str, Any]) -> bool:
        status = str(item.get("status") or "").lower()
        if status and status != AgentState.COMPLETED.value:
            return True
        if item.get("tool_count"):
            return True
        return bool(str(item.get("rationale") or "").strip())

    @staticmethod
    def _empty_output_section(item: dict[str, Any]) -> str:
        agent_name = item.get("agent_name") or "Agent"
        status = item.get("status") or "unknown"
        rationale = str(item.get("rationale") or "").strip()
        line = f"{agent_name} 本轮状态为 {status}，但未形成可直接展示的正文成果。"
        if rationale:
            line += f"\n\n调度记录：{rationale}"
        if item.get("tool_count"):
            line += f"\n\n工具调用次数：{item.get('tool_count')}，需结合工具结果复核是否存在失败或空输出。"
        return line

    def _section_summary_for_review(self, item: dict[str, Any]) -> str:
        if not item.get("output") and not item.get("artifacts"):
            return self._empty_output_section(item)
        status = str(item.get("status") or "unknown")
        stage = item.get("stage") or 1
        tool_count = int(item.get("tool_count") or 0)
        artifacts = self._unique_artifacts(item.get("artifacts") or [])
        capability = self._capability_label_for_review(item)
        parts = [
            f"状态：{status}",
            f"阶段：{stage}",
            f"专项：{capability}",
            f"工具调用：{tool_count} 次",
        ]
        if artifacts:
            titles = "、".join(self._artifact_title(artifact) for artifact in artifacts[:3])
            suffix = "等" if len(artifacts) > 3 else ""
            parts.append(f"产物：{titles}{suffix}")
        coverage = self._coverage_points_for_review(item)
        if coverage:
            parts.append(f"覆盖：{'、'.join(coverage[:5])}")
        return "；".join(parts) + "。"

    def _capability_label_for_review(self, item: dict[str, Any]) -> str:
        rules = [
            (("plan", "planner", "strategy", "roadmap", "pm", "product", "规划", "计划", "路线图", "方案", "产品"), "规划与任务拆解"),
            (("research", "analyst", "analysis", "data", "insight", "调研", "研究", "分析", "洞察", "数据"), "分析洞察与依据"),
            (("writer", "writing", "content", "copy", "editor", "文案", "写作", "内容", "沟通", "公告", "话术"), "内容撰写与沟通材料"),
            (("marketing", "growth", "campaign", "市场", "营销", "增长", "获客", "运营活动"), "市场运营与增长方案"),
            (("front", "ui", "ux", "design", "web", "prototype", "前端", "原型", "界面", "体验"), "体验设计与界面原型"),
            (("back", "api", "server", "rag", "backend", "后端", "接口", "数据模型", "检索", "知识库"), "服务接口与数据链路"),
            (("review", "qa", "test", "security", "verify", "验收", "安全", "审计", "测试", "复核"), "质量校验与风险检查"),
            (("deploy", "release", "ops", "launch", "部署", "发布", "健康检查", "上线"), "发布准备与运行保障"),
            (("legal", "compliance", "合规", "法务", "隐私", "条款"), "合规与边界检查"),
            (("finance", "budget", "cost", "财务", "预算", "成本", "报价"), "预算成本与资源测算"),
            (("support", "success", "customer", "客服", "客户成功", "服务"), "客户支持与交付保障"),
        ]
        identity_text = f"{item.get('agent_name') or ''} {item.get('role') or ''}".lower()
        output_text = f"{item.get('output') or ''} {item.get('rationale') or ''}".lower()
        task_text = str(item.get("task") or "").lower()
        for text in (identity_text, output_text, task_text):
            if not text.strip():
                continue
            # Agent identity and concrete output are more specific than the whole user task.
            for keywords, label in rules:
                if any(keyword in text for keyword in keywords):
                    return label
        return self._fallback_capability_label(item)

    @staticmethod
    def _fallback_capability_label(item: dict[str, Any]) -> str:
        for key in ("role", "agent_name"):
            label = _clean_role_label(str(item.get(key) or ""))
            if label:
                return f"{label}专项成果"
        return "专项交付成果"

    @staticmethod
    def _compressed_output_excerpt(text: str, *, max_chars: int = 90) -> str:
        normalized = " ".join(str(text or "").split())
        if not normalized:
            return ""
        normalized = normalized.replace("我已经完成了", "已完成").replace("我作为", "")
        return normalized if len(normalized) <= max_chars else f"{normalized[:max_chars].rstrip()}..."

    @staticmethod
    def _coverage_points_for_review(item: dict[str, Any]) -> list[str]:
        text = f"{item.get('task') or ''} {item.get('output') or ''}".lower()
        checks = [
            (("目标", "objective", "goal"), "目标定义"),
            (("范围", "scope"), "范围边界"),
            (("计划", "规划", "roadmap", "节奏", "timeline", "schedule"), "计划节奏"),
            (("调研", "研究", "research"), "调研依据"),
            (("分析", "洞察", "analysis", "insight"), "分析洞察"),
            (("用户沟通", "沟通", "公告", "message", "communication"), "用户沟通"),
            (("发布", "release", "launch"), "发布准备"),
            (("风险", "risk"), "风险清单"),
            (("验收", "acceptance", "review", "qa"), "验收检查"),
            (("文档上传", "upload"), "文档上传"),
            (("知识库列表", "knowledge base list"), "知识库列表"),
            (("问答输入", "qa input", "question"), "问答输入"),
            (("引用来源", "citation", "source"), "引用来源"),
            (("索引状态", "index status"), "索引状态"),
            (("错误提示", "error"), "错误提示"),
            (("api", "接口"), "API 草案"),
            (("数据模型", "model"), "数据模型"),
            (("rag", "检索"), "RAG 检索链路"),
            (("流式", "stream"), "流式协议"),
            (("安全", "security", "audit"), "安全边界"),
            (("部署", "deploy"), "部署预检"),
            (("健康", "health"), "健康检查"),
            (("导出", "export"), "导出链路"),
        ]
        points: list[str] = []
        for keywords, label in checks:
            if any(keyword in text for keyword in keywords):
                points.append(label)
        return list(dict.fromkeys(points))

    @staticmethod
    def _artifact_title(artifact: dict[str, Any]) -> str:
        return str(
            artifact.get("title")
            or artifact.get("filename")
            or artifact.get("artifact_id")
            or artifact.get("file_id")
            or "未命名产物"
        )

    @staticmethod
    def _unique_artifacts(artifacts: list[Any]) -> list[dict[str, Any]]:
        unique: list[dict[str, Any]] = []
        seen: set[str] = set()
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            key = str(
                artifact.get("artifact_id")
                or artifact.get("preview_message_id")
                or artifact.get("file_id")
                or artifact.get("download_url")
                or artifact.get("public_url")
                or artifact.get("title")
                or artifact.get("filename")
                or len(unique)
            )
            if key in seen:
                continue
            seen.add(key)
            unique.append(dict(artifact))
        return unique[:MAX_SUMMARY_ITEMS]

    def _final_logic_chain(self, outputs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        completed_ids = {str(item.get("agent_id") or "") for item in outputs}
        chain: list[dict[str, Any]] = []
        plan_items = sorted(
            [item for item in self._turn_plan if isinstance(item, dict)],
            key=lambda item: (int(item.get("stage") or 1), int(item.get("priority") or 0)),
        )
        for item in plan_items[:MAX_SUMMARY_ITEMS]:
            agent_id = str(item.get("agent_id") or "")
            depends_on = [str(dep) for dep in item.get("depends_on") or [] if str(dep or "").strip()]
            dependencies_closed = all(dep in completed_ids for dep in depends_on)
            has_output = agent_id in completed_ids
            chain.append(
                {
                    "stage": int(item.get("stage") or 1),
                    "agent_id": agent_id,
                    "agent_name": self._agent_label(agent_id),
                    "status": "closed" if has_output and dependencies_closed else "open",
                    "depends_on": depends_on,
                    "closure": (
                        "已接收上游依赖并回填专项成果。"
                        if has_output and dependencies_closed
                        else "仍需补齐输出或依赖结果。"
                    ),
                }
            )
        return chain

    def _final_compliance_checks(
        self,
        *,
        outputs: list[dict[str, Any]],
        failed: list[dict[str, Any]],
        pending: list[dict[str, Any]],
        in_progress: list[dict[str, Any]],
        coordination_gaps: list[str],
    ) -> list[dict[str, str]]:
        planned_ids = set(self._planned_agent_ids())
        output_ids = {str(item.get("agent_id") or "") for item in outputs if item.get("agent_id")}
        missing_ids = sorted(planned_ids - output_ids)
        all_dependencies_closed = all(
            str(dep) in output_ids
            for item in self._turn_plan
            for dep in (item.get("depends_on") or [])
            if str(dep or "").strip()
        )
        return [
            {
                "name": "多源成果归集",
                "status": "passed" if outputs else "warning",
                "detail": f"已归集 {len(outputs)} 个子 Agent 成果。",
            },
            {
                "name": "计划覆盖完整性",
                "status": "passed" if not missing_ids else "warning",
                "detail": (
                    "所有计划成员均已产生可归档结果。"
                    if not missing_ids
                    else "仍缺少：" + ", ".join(self._agent_label(agent_id) for agent_id in missing_ids)
                ),
            },
            {
                "name": "依赖链路闭环",
                "status": "passed" if all_dependencies_closed else "warning",
                "detail": "阶段依赖均已闭合。" if all_dependencies_closed else "存在未闭合的阶段依赖。",
            },
            {
                "name": "异常与协作缺口",
                "status": "passed" if not (failed or pending or in_progress or coordination_gaps) else "warning",
                "detail": (
                    "未检测到失败、等待、进行中或协作缺口。"
                    if not (failed or pending or in_progress or coordination_gaps)
                    else "存在需复核项，已在风险与后续中列出。"
                ),
            },
            {
                "name": "输出格式标准化",
                "status": "passed",
                "detail": "Team Leader 已统一按目标、来源、链路、校验、成品、风险格式输出。",
            },
        ]

    def _compose_final_answer(self, deliverable: dict[str, Any]) -> str:
        outputs = list(deliverable.get("source_reviews") or [])
        final_product = deliverable.get("final_product") if isinstance(deliverable.get("final_product"), dict) else {}
        product_content = str(final_product.get("content") or "").strip()
        artifacts = final_product.get("artifacts") if isinstance(final_product.get("artifacts"), list) else []
        is_collaborative = bool(deliverable.get("is_collaborative"))
        if not outputs:
            return "本轮没有子 Agent 产出可交付成果。"

        if not is_collaborative:
            lines = [product_content or "已完成产物生成，关联产物见下方。"]
            if artifacts:
                lines.extend(["", "关联产物："])
                for artifact in artifacts[:MAX_SUMMARY_ITEMS]:
                    title = artifact.get("title") or artifact.get("filename") or artifact.get("artifact_id")
                    lines.append(f"- {title}")
            return "\n".join(lines).strip()

        lines: list[str] = [
            "## 最终成品",
            product_content or "已完成本轮多 Agent 协作任务，并形成标准化交付包。",
            "",
            "## 归集",
        ]
        for index, output in enumerate(outputs[:MAX_SUMMARY_ITEMS], start=1):
            deps = ", ".join(self._agent_label(str(dep)) for dep in output.get("depends_on") or []) or "无"
            summary = self._section_summary_for_review(output)
            lines.append(f"{index}. **{output.get('agent_name') or 'Agent'}**：依赖 {deps}。{summary}")

        lines.extend(["", "## 链路"])
        for index, item in enumerate(deliverable.get("logic_chain") or [], start=1):
            deps = ", ".join(self._agent_label(str(dep)) for dep in item.get("depends_on") or []) or "无"
            lines.append(
                f"{index}. 阶段 {item.get('stage')}: {item.get('agent_name')} "
                f"({item.get('status')})，上游依赖：{deps}。{item.get('closure')}"
            )

        lines.extend(["", "## 校验"])
        for check in deliverable.get("compliance_checks") or []:
            marker = "通过" if check.get("status") == "passed" else "需复核"
            lines.append(f"- {check.get('name')}: {marker}。{check.get('detail')}")

        lines.extend(["", "## 产物"])
        if artifacts:
            for artifact in artifacts[:MAX_SUMMARY_ITEMS]:
                title = self._artifact_title(artifact)
                refs = [
                    f"artifact_id: {artifact.get('artifact_id')}" if artifact.get("artifact_id") else "",
                    f"预览: {artifact.get('preview_url') or artifact.get('public_url')}"
                    if artifact.get("preview_url") or artifact.get("public_url")
                    else "",
                    f"导出: {artifact.get('export_url') or artifact.get('download_url')}"
                    if artifact.get("export_url") or artifact.get("download_url")
                    else "",
                ]
                suffix = "；".join(item for item in refs if item)
                lines.append(f"- {title}" + (f"（{suffix}）" if suffix else ""))
        else:
            sections = final_product.get("sections") if isinstance(final_product.get("sections"), list) else []
            if sections:
                names = "、".join(
                    str(item.get("agent_name") or item.get("agent_id") or "Agent")
                    for item in sections[:MAX_SUMMARY_ITEMS]
                    if isinstance(item, dict)
                )
                lines.append(f"- 本轮无独立预览卡片；已将 {names} 的可归档成果整合进最终成品。")
            else:
                lines.append("- 本轮未检测到独立预览卡片；最终成品以内联交付内容为准。")

        lines.extend(["", "## 风险"])
        for item in deliverable.get("risks") or []:
            lines.append(f"- {item}")
        return "\n".join(lines).strip()

    def _agent_label(self, agent_id: str) -> str:
        agent = self.agents.get(agent_id)
        return agent.name if agent else agent_id or "Agent"

    def _select_targets_for_task(self, task: str, named_targets: list[str]) -> list[str]:
        schedulable = self._schedulable_agent_ids()
        if not schedulable:
            return []
        if named_targets and not self._is_collaboration_request(task):
            return named_targets
        if self._looks_like_fullstack_delivery(task):
            selected = self._fullstack_delivery_targets(schedulable, named_targets)
            if selected:
                return selected[:MAX_PLAN_TASKS]
        if not self._looks_like_multi_agent_task(task):
            return self._single_best_target(task, named_targets, schedulable)

        selected: list[str] = []
        if named_targets:
            selected.extend(named_targets)
        selected.extend(
            agent_id
            for agent_id in schedulable
            if self._agent_matches_task_need(agent_id, task)
        )
        if self._requires_review_or_release(task):
            selected.extend(
                agent_id
                for agent_id in schedulable
                if self._agent_collaboration_kind(agent_id) in {"review", "release"}
            )
        selected = self._valid_target_ids(list(dict.fromkeys(selected)))
        if selected:
            return self._ordered_targets_for_plan(selected)[:MAX_PLAN_TASKS]
        if self._is_collaboration_request(task):
            return self._ordered_targets_for_plan(schedulable[: min(3, len(schedulable))])
        return self._single_best_target(task, named_targets, schedulable)

    def _fullstack_delivery_targets(self, schedulable: list[str], named_targets: list[str]) -> list[str]:
        selected: list[str] = []
        if named_targets:
            selected.extend(named_targets)

        backend_id = self._first_agent_matching(
            schedulable,
            self._is_backend_agent,
        )
        if not backend_id:
            backend_id = self._first_agent_matching(
                schedulable,
                lambda agent_id: self._agent_collaboration_kind(agent_id) == "implementation"
                and not self._is_frontend_agent(agent_id)
                and not self._agent_can_create_docs(agent_id),
            )
        frontend_id = self._first_agent_matching(
            schedulable,
            self._is_frontend_agent,
        )
        doc_id = self._first_agent_matching(
            schedulable,
            lambda agent_id: agent_id not in {backend_id, frontend_id}
            and self._agent_can_create_docs(agent_id),
        )
        review_id = self._first_agent_matching(
            schedulable,
            lambda agent_id: self._agent_collaboration_kind(agent_id) == "review",
        )

        for agent_id in (backend_id, frontend_id, doc_id, review_id):
            if agent_id:
                selected.append(agent_id)
        if not selected:
            selected.extend(schedulable[: min(3, len(schedulable))])
        return list(dict.fromkeys(self._valid_target_ids(selected)))

    @staticmethod
    def _first_agent_matching(agent_ids: list[str], predicate: Callable[[str], bool]) -> str | None:
        for agent_id in agent_ids:
            if predicate(agent_id):
                return agent_id
        return None

    def _agent_role_text(self, agent_id: str) -> str:
        agent = self.agents.get(agent_id)
        if not agent:
            return ""
        return f"{agent.name} {agent.role} {getattr(agent, 'description', '')}".lower()

    def _agent_can_create_docs(self, agent_id: str) -> bool:
        agent = self.agents.get(agent_id)
        if not agent:
            return False
        tools = set(agent.tools or [])
        role_text = self._agent_role_text(agent_id)
        return bool(
            tools.intersection({"artifact.create_pdf", "artifact.create_docx", "artifact.create_pptx"})
            or self._agent_collaboration_kind(agent_id) == "content"
            or any(token in role_text for token in ("writing", "writer", "content", "daily", "chat", "doc", "pdf"))
        )

    def _is_backend_agent(self, agent_id: str) -> bool:
        role_text = self._agent_role_text(agent_id)
        return any(token in role_text for token in ("backend", "back-end", "server", "api", "后端", "接口", "服务端"))

    def _is_frontend_agent(self, agent_id: str) -> bool:
        role_text = self._agent_role_text(agent_id)
        return self._agent_collaboration_kind(agent_id) == "design" or any(
            token in role_text for token in ("frontend", "front-end", "front", "ui", "ux", "web", "前端", "界面")
        )

    def _ordered_targets_for_plan(self, targets: list[str]) -> list[str]:
        original_index = {agent_id: index for index, agent_id in enumerate(self._schedulable_agent_ids())}
        stage_rank = {
            "planning": 0,
            "implementation": 1,
            "research": 1,
            "content": 1,
            "design": 1,
            "marketing": 1,
            "finance": 1,
            "support": 1,
            "review": 2,
            "release": 3,
        }
        return sorted(
            targets,
            key=lambda agent_id: (
                stage_rank.get(self._agent_collaboration_kind(agent_id), 1),
                original_index.get(agent_id, 999),
            ),
        )

    def _single_best_target(
        self,
        task: str,
        named_targets: list[str],
        schedulable: list[str],
    ) -> list[str]:
        if named_targets:
            return named_targets[:1]
        matched = [
            agent_id
            for agent_id in schedulable
            if self._agent_matches_task_need(agent_id, task)
        ]
        if matched:
            return matched[:1]
        chat_agent_id = self._chat_agent_id()
        if chat_agent_id and chat_agent_id in schedulable:
            return [chat_agent_id]
        return schedulable[:1]

    def _agent_matches_task_need(self, agent_id: str, task: str) -> bool:
        normalized = str(task or "").lower()
        kind = self._agent_collaboration_kind(agent_id)
        keyword_map = {
            "planning": ("规划", "计划", "方案", "节奏", "拆解", "复盘", "prepare", "plan", "roadmap"),
            "research": ("调研", "研究", "分析", "洞察", "指标", "数据", "research", "analysis", "insight"),
            "content": ("文档", "写", "撰写", "材料", "沟通", "公告", "话术", "pdf", "word", "doc", "download"),
            "design": ("html", "页面", "前端", "可视化", "预览", "原型", "总览页", "web", "ui"),
            "implementation": ("实现", "接口", "后端", "服务", "api", "数据", "校验规则", "backend"),
            "review": ("复核", "审查", "验收", "测试", "安全", "review", "qa", "verify"),
            "release": ("部署", "发布", "上线", "预览部署", "deploy", "release", "launch"),
            "marketing": ("营销", "增长", "运营", "市场", "campaign", "growth"),
            "finance": ("预算", "成本", "报价", "finance", "budget", "cost"),
            "support": ("客服", "客户", "支持", "服务", "support", "customer"),
        }
        return any(keyword in normalized for keyword in keyword_map.get(kind, ()))

    def _requires_review_or_release(self, task: str) -> bool:
        normalized = str(task or "").lower()
        return any(
            keyword in normalized
            for keyword in ("复核", "审查", "验收", "部署", "发布", "上线", "review", "qa", "deploy", "release")
        )

    def _display_task_for_agent(self, task: str, agent_id: str, agent: AgentConfig) -> str:
        if self._looks_like_fullstack_delivery(task):
            specialized = self._fullstack_task_for_agent(agent_id, agent, visible=True)
            if specialized:
                return specialized
        normalized = str(task or "").lower()
        kind = self._agent_collaboration_kind(agent_id)
        if kind == "planning":
            return "梳理任务目标、交付范围和执行节奏"
        if kind == "research":
            return "整理依据、指标和关键判断"
        if kind == "content":
            if any(keyword in normalized for keyword in ("文档", "word", "doc", "pdf", "download")):
                return "生成可下载交付文档"
            return "撰写用户沟通与交付材料"
        if kind == "design":
            if any(keyword in normalized for keyword in ("html", "页面", "预览", "总览")):
                return "生成可预览 HTML 总览页"
            return "设计可视化交付界面"
        if kind == "implementation":
            return "补齐服务接口、数据链路和自动化规则"
        if kind == "review":
            return "复核上游产物的完整性、一致性和风险"
        if kind == "release":
            return "部署预览并回填访问链接"
        return f"{agent.name} 完成匹配专项交付"

    def _plan_stage_for_agent(
        self,
        agent_id: str,
        agent: AgentConfig,
        targets: list[str],
    ) -> tuple[int, list[str]]:
        kind = self._agent_collaboration_kind(agent_id)
        if self._looks_like_fullstack_delivery(self.current_task):
            return self._fullstack_stage_for_agent(agent_id, targets)
        planning_ids = [
            target_id
            for target_id in targets
            if target_id != agent_id
            and self._agent_collaboration_kind(target_id) == "planning"
        ]
        implementation_ids = [
            target_id
            for target_id in targets
            if target_id != agent_id
            and self._agent_collaboration_kind(target_id)
            in {"implementation", "research", "content", "design", "marketing", "finance", "support"}
        ]
        review_ids = [
            target_id
            for target_id in targets
            if target_id != agent_id
            and self._agent_collaboration_kind(target_id) == "review"
        ]
        if kind == "planning":
            return 1, []
        if kind in {"implementation", "research", "content", "design", "marketing", "finance", "support"}:
            return (2, planning_ids) if planning_ids else (1, [])
        if kind == "review":
            dependencies = planning_ids + implementation_ids
            return (3 if planning_ids else 2), list(dict.fromkeys(dependencies))
        if kind == "release":
            dependencies = planning_ids + implementation_ids + review_ids
            return (4 if planning_ids else 3), list(dict.fromkeys(dependencies))
        return (2, planning_ids) if planning_ids else (1, [])

    def _fullstack_stage_for_agent(self, agent_id: str, targets: list[str]) -> tuple[int, list[str]]:
        backend_ids = [
            target_id
            for target_id in targets
            if target_id != agent_id and self._is_backend_agent(target_id)
        ]
        frontend_ids = [
            target_id
            for target_id in targets
            if target_id != agent_id and self._is_frontend_agent(target_id)
        ]
        doc_ids = [
            target_id
            for target_id in targets
            if target_id != agent_id and self._agent_can_create_docs(target_id)
        ]
        review_ids = [
            target_id
            for target_id in targets
            if target_id != agent_id and self._agent_collaboration_kind(target_id) == "review"
        ]

        if self._is_backend_agent(agent_id):
            return 1, []
        if self._is_frontend_agent(agent_id):
            return 2, list(dict.fromkeys(backend_ids))
        if self._agent_can_create_docs(agent_id):
            return 3, list(dict.fromkeys(backend_ids + frontend_ids))
        if self._agent_collaboration_kind(agent_id) == "review":
            return 4, list(dict.fromkeys(backend_ids + frontend_ids + doc_ids))
        if self._agent_collaboration_kind(agent_id) == "release":
            return 5, list(dict.fromkeys(backend_ids + frontend_ids + doc_ids + review_ids))
        return 2, list(dict.fromkeys(backend_ids))

    def _agent_collaboration_kind(self, agent_id: str) -> str:
        agent = self.agents.get(agent_id)
        if not agent:
            return "implementation"
        role = f"{agent.name} {agent.role}".lower()
        if any(keyword in role for keyword in ("plan", "planner", "strategy", "roadmap", "pm", "product", "规划", "计划", "方案", "产品")):
            return "planning"
        if any(keyword in role for keyword in ("test", "qa", "review", "verify", "audit", "验收", "审查", "测试", "复核")):
            return "review"
        if any(keyword in role for keyword in ("deploy", "release", "ops", "launch", "部署", "发布", "上线")):
            return "release"
        if any(keyword in role for keyword in ("research", "analyst", "analysis", "data", "调研", "研究", "分析", "数据")):
            return "research"
        if any(keyword in role for keyword in ("writer", "writing", "content", "copy", "editor", "文案", "写作", "内容", "沟通")):
            return "content"
        if any(keyword in role for keyword in ("front", "ui", "ux", "design", "prototype", "前端", "界面", "体验", "原型")):
            return "design"
        if any(keyword in role for keyword in ("marketing", "growth", "campaign", "市场", "营销", "增长", "运营")):
            return "marketing"
        if any(keyword in role for keyword in ("finance", "budget", "cost", "财务", "预算", "成本")):
            return "finance"
        if any(keyword in role for keyword in ("support", "success", "customer", "客服", "客户成功", "服务")):
            return "support"
        return "implementation"

    def _task_for_agent(self, task: str, agent: AgentConfig) -> str:
        role_hint = f"{agent.name} ({agent.role})"
        if not task:
            return f"Handle the next suitable subtask as {role_hint}."
        if self._looks_like_fullstack_delivery(task):
            specialized = self._fullstack_task_for_agent(agent.id, agent, visible=False)
            if specialized:
                return specialized
        return f"{task}\n\n请以 {role_hint} 的职责完成可见交付；不要重复其他 Agent 的工作。"

    def _fullstack_task_for_agent(self, agent_id: str, agent: AgentConfig, *, visible: bool) -> str | None:
        if self._is_backend_agent(agent_id):
            return "设计五子棋后端能力：规则服务、棋局状态模型、落子/胜负判断 API 契约，并输出前端可直接对接的接口说明。"
        if self._is_frontend_agent(agent_id):
            if visible:
                return "基于后端契约实现可运行的五子棋前端页面"
            return (
                "基于上游后端 API 契约实现可运行的五子棋前端。必须生成真实 HTML/Web 产物，"
                "包含 15x15 棋盘、落子交互、胜负判断、重新开始和接口对接说明。不要只做说明页。"
            )
        if self._agent_can_create_docs(agent_id):
            if visible:
                return "基于前后端产物生成 PDF 说明文档"
            return (
                "基于上游后端契约和前端实现生成 PDF 说明文档。文档需要包含项目概述、架构、接口、玩法、"
                "运行步骤和验收清单，并生成真实 PDF 产物。"
            )
        if self._agent_collaboration_kind(agent_id) == "review":
            return "审查五子棋项目前后端和说明文档的一致性、可运行性与交付风险。"
        if self._agent_collaboration_kind(agent_id) == "release":
            return "部署或预览五子棋项目产物，并回填可访问链接与部署状态。"
        return None

    @staticmethod
    def _expected_outputs_for_agent(agent: AgentConfig) -> list[str]:
        role = f"{agent.name} {agent.role}".lower()
        if any(keyword in role for keyword in ("plan", "planner", "strategy", "roadmap", "pm", "product", "规划", "计划", "方案", "产品")):
            return ["task plan and sequencing", "acceptance criteria or dependencies"]
        if any(keyword in role for keyword in ("research", "analyst", "analysis", "data", "调研", "研究", "分析", "数据")):
            return ["analysis findings", "evidence, assumptions, and gaps"]
        if any(keyword in role for keyword in ("writer", "writing", "content", "copy", "editor", "文案", "写作", "内容", "沟通")):
            return ["drafted content or communication package", "tone and audience notes"]
        if any(keyword in role for keyword in ("marketing", "growth", "campaign", "市场", "营销", "增长", "运营")):
            return ["go-to-market or operation plan", "metrics and risk notes"]
        if any(keyword in role for keyword in ("front", "ui", "design")):
            return ["UI implementation notes or artifact", "risks and next checks"]
        if any(keyword in role for keyword in ("back", "api", "server")):
            return ["API/service implementation result", "integration notes"]
        if any(keyword in role for keyword in ("test", "qa", "review")):
            return ["verification result", "issues found and suggested fixes"]
        if any(keyword in role for keyword in ("deploy", "release")):
            return ["deployment/readiness result", "rollback or risk notes"]
        if any(keyword in role for keyword in ("finance", "budget", "cost", "财务", "预算", "成本")):
            return ["cost or resource estimate", "budget risks"]
        if any(keyword in role for keyword in ("support", "success", "customer", "客服", "客户成功", "服务")):
            return ["customer-facing support plan", "handoff or escalation notes"]
        return ["visible work result", "blockers or follow-up if any"]

    @staticmethod
    def _agent_fit_rationale(agent: AgentConfig) -> str:
        tools = f"; tools={', '.join(agent.tools[:4])}" if agent.tools else ""
        return f"Matched by role={agent.role}{tools}."

    def _mention_decision(self) -> SchedulingDecision | None:
        targets = [
            agent_id
            for agent_id in dict.fromkeys(self._mention_target_ids)
            if agent_id in self.agents and agent_id != self.scheduler_id
        ]
        if not targets:
            return None
        pending = [
            agent_id
            for agent_id in targets
            if agent_id not in self._mention_dispatched_ids
            and not self._mention_target_terminal(agent_id)
        ]
        if not pending:
            unfinished = [
                agent_id
                for agent_id in targets
                if not self._mention_target_terminal(agent_id)
            ]
            if unfinished:
                return SchedulingDecision(
                    decision_type="wait",
                    action="wait",
                    target_agent_id=unfinished[0],
                    target_agent_ids=unfinished,
                    task=self.current_task,
                    task_description=self.current_task,
                    rationale="User-mentioned Agent has already been assigned; waiting for its report.",
                )
            return SchedulingDecision(
                decision_type="complete",
                action="complete",
                target_agent_id=targets[0],
                target_agent_ids=targets,
                task=self.current_task,
                task_description=self.current_task,
                rationale="User-mentioned Agent reached a terminal report; ending this turn.",
            )
        return SchedulingDecision(
            decision_type="parallel" if len(pending) > 1 else "assign",
            action="assign",
            target_agent_id=pending[0],
            target_agent_ids=pending,
            task=self.current_task,
            task_description=self.current_task,
            rationale="用户 @ 指定了目标 Agent，本轮只调度被指定成员。",
            expected_outputs=["目标 Agent 的直接回复"],
        )

    def _mention_target_terminal(self, agent_id: str) -> bool:
        report = self.reports.get(agent_id)
        if not report:
            return False
        return report.state in {AgentState.COMPLETED, AgentState.FAILED}

    def _completion_decision_for_terminal_reports(
        self,
        reports: list[AgentReport],
    ) -> SchedulingDecision | None:
        terminal_states = {AgentState.COMPLETED, AgentState.FAILED}
        terminal_ids = {
            report.agent_id
            for report in reports
            if report.state in terminal_states
        }
        if not terminal_ids:
            return None

        schedulable_ids = self._schedulable_agent_ids()
        if schedulable_ids and all(
            self.reports.get(agent_id) and self.reports[agent_id].state in terminal_states
            for agent_id in schedulable_ids
        ):
            return SchedulingDecision(
                decision_type="complete",
                action="complete",
                task=self.current_task,
                task_description=self.current_task,
                rationale="All schedulable Agents reached terminal reports.",
            )

        named_targets = self._agent_ids_mentioned_in(self.current_task)
        if len(named_targets) == 1 and named_targets[0] in terminal_ids:
            return SchedulingDecision(
                decision_type="complete",
                action="complete",
                target_agent_id=named_targets[0],
                target_agent_ids=named_targets,
                task=self.current_task,
                task_description=self.current_task,
                rationale="Single addressed Agent reached a terminal report; ending this turn.",
            )

        if len(self._assigned_agent_ids) != 1:
            return None
        assigned = next(iter(self._assigned_agent_ids))
        if assigned not in terminal_ids:
            return None
        if self._requires_multi_agent_turn(named_targets):
            return None
        return SchedulingDecision(
            decision_type="complete",
            action="complete",
            target_agent_id=assigned,
            target_agent_ids=[assigned],
            task=self.current_task,
            task_description=self.current_task,
            rationale="The single assigned Agent completed the turn.",
        )

    def _greeting_decision(self, reports: list[AgentReport]) -> SchedulingDecision | None:
        if not _is_simple_greeting_utf8(self.current_task):
            return None
        target = self._chat_agent_id() or _first_ready_agent_id(reports, self.scheduler_id)
        if not target:
            return SchedulingDecision(
                decision_type="wait",
                action="wait",
                rationale="Greeting detected but no ready chat agent is available.",
            )
        target_report = next((report for report in reports if report.agent_id == target), None)
        if target_report and target_report.state in {AgentState.COMPLETED, AgentState.FAILED}:
            return SchedulingDecision(
                decision_type="complete",
                action="complete",
                target_agent_id=target,
                target_agent_ids=[target],
                task=self.current_task,
                task_description=self.current_task,
                rationale="Greeting turn reached a terminal agent report.",
            )
        return SchedulingDecision(
            decision_type="assign",
            action="assign",
            target_agent_id=target,
            target_agent_ids=[target],
            task=self.current_task,
            task_description=self.current_task,
            rationale="Simple greeting: route to the chat-oriented agent instead of waiting.",
            expected_outputs=["A concise visible greeting reply."],
        )

    def _chat_agent_id(self) -> str | None:
        for agent_id, config in self.agents.items():
            text = f"{config.name} {config.role}".lower()
            if "daily chat" in text or "chat" in text or "日常" in text:
                return agent_id
        return None

    def _normalize_decision(self, decision: SchedulingDecision) -> SchedulingDecision:
        if not decision.action:
            decision.action = "assign" if decision.decision_type == "parallel" else decision.decision_type
        targets: list[str] = []
        if decision.target_agent_id:
            targets.append(decision.target_agent_id)
        targets.extend(decision.target_agent_ids or [])
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

    def _repair_decision(
        self,
        decision: SchedulingDecision,
        reports: list[AgentReport],
    ) -> SchedulingDecision:
        """Repair unsafe scheduler output with deterministic runtime guardrails."""
        mention_targets = self._valid_target_ids(self._mention_target_ids)
        if mention_targets:
            if decision.decision_type in {"assign", "parallel"}:
                targets = self._valid_target_ids(
                    [decision.target_agent_id]
                    + list(decision.target_agent_ids or [])
                    + list(decision.verification_agents or [])
                )
                targets = [target for target in targets if target in mention_targets]
                if not targets:
                    targets = [
                        agent_id
                        for agent_id in mention_targets
                        if agent_id not in self._mention_dispatched_ids
                        and not self._mention_target_terminal(agent_id)
                    ]
                if not targets:
                    targets = [
                        agent_id
                        for agent_id in mention_targets
                        if not self._mention_target_terminal(agent_id)
                    ]
                if not targets:
                    targets = mention_targets
                decision.decision_type = "parallel" if len(targets) > 1 else "assign"
                decision.action = "assign"
                decision.target_agent_id = targets[0]
                decision.target_agent_ids = targets
                decision.rationale = _append_reason(
                    decision.rationale,
                    "Explicit user mention scope restricts this turn to the mentioned Agent(s).",
                )
                return decision
            if decision.decision_type == "complete":
                unfinished = [
                    agent_id
                    for agent_id in mention_targets
                    if not self._mention_target_terminal(agent_id)
                ]
                if unfinished:
                    return self._mention_decision() or SchedulingDecision(
                        decision_type="wait",
                        action="wait",
                        target_agent_id=unfinished[0],
                        target_agent_ids=unfinished,
                        task=self.current_task,
                        task_description=self.current_task,
                        rationale="Mentioned Agent has not reached a terminal report yet.",
                    )
                decision.target_agent_id = decision.target_agent_id or mention_targets[0]
                decision.target_agent_ids = mention_targets
                return decision
            if decision.decision_type == "wait":
                decision.target_agent_id = decision.target_agent_id or mention_targets[0]
                decision.target_agent_ids = [
                    target for target in self._valid_target_ids(decision.target_agent_ids) if target in mention_targets
                ] or mention_targets
                return decision
            return decision

        decision_text = "\n".join(
            item
            for item in (
                self.current_task,
                decision.task,
                decision.task_description,
                decision.rationale,
                " ".join(decision.expected_outputs or []),
            )
            if item
        )
        named_targets = self._agent_ids_mentioned_in(decision_text)
        is_multi_agent_task = self._requires_multi_agent_turn(named_targets, decision_text)
        plan_targets = self._planned_agent_ids()

        if decision.decision_type in {"assign", "parallel"}:
            targets = self._valid_target_ids(decision.target_agent_ids)
            if decision.target_agent_id:
                targets.insert(0, decision.target_agent_id)
            targets = self._valid_target_ids(targets)

            if plan_targets and is_multi_agent_task:
                ready_plan_targets = self._ready_plan_targets()
                if not ready_plan_targets:
                    waiting_plan_targets = [
                        agent_id
                        for agent_id in plan_targets
                        if agent_id in self._inflight_agent_ids
                    ]
                    if waiting_plan_targets:
                        decision.decision_type = "wait"
                        decision.action = "wait"
                        decision.target_agent_id = waiting_plan_targets[0]
                        decision.target_agent_ids = waiting_plan_targets
                        decision.rationale = _append_reason(
                            decision.rationale,
                            "Waiting for the current collaboration stage to finish.",
                        )
                        return decision
                targets = ready_plan_targets
            elif named_targets and len(named_targets) > len(targets):
                targets = named_targets
            elif is_multi_agent_task and not targets:
                targets = self._ready_or_idle_agent_ids(reports) or self._schedulable_agent_ids()

            targets = [
                target
                for target in targets
                if not self._agent_has_terminal_report(target)
            ]
            waiting_targets = [
                target
                for target in targets
                if target in self._inflight_agent_ids
            ]
            targets = [
                target
                for target in targets
                if target not in self._inflight_agent_ids
            ]
            if not targets and waiting_targets:
                decision.decision_type = "wait"
                decision.action = "wait"
                decision.target_agent_id = waiting_targets[0]
                decision.target_agent_ids = waiting_targets
                decision.rationale = _append_reason(
                    decision.rationale,
                    "Some assigned Agents are still running; waiting for their reports.",
                )
                return decision

            if len(targets) > 1:
                decision.decision_type = "parallel"
                decision.action = "assign"
                decision.target_agent_id = targets[0]
                decision.target_agent_ids = targets
                decision.rationale = _append_reason(
                    decision.rationale,
                    "Detected a multi-agent task; dispatching matching group members in parallel.",
                )
            elif targets:
                decision.target_agent_id = targets[0]
                decision.target_agent_ids = targets
            return decision

        if decision.decision_type == "complete" and is_multi_agent_task:
            required_targets = plan_targets or named_targets or self._schedulable_agent_ids()
            terminal_states = {AgentState.COMPLETED, AgentState.FAILED}
            pending = [
                agent_id
                for agent_id in required_targets
                if self.reports.get(
                    agent_id,
                    AgentReport(agent_id=agent_id, state=AgentState.READY, will=AgentWill.EXECUTE),
                ).state
                not in terminal_states
            ]
            if pending:
                waiting_for_reports = [agent_id for agent_id in pending if agent_id in self._inflight_agent_ids]
                if waiting_for_reports:
                    return SchedulingDecision(
                        decision_type="wait",
                        action="wait",
                        target_agent_id=waiting_for_reports[0],
                        target_agent_ids=waiting_for_reports,
                        task=self.current_task,
                        task_description=self.current_task,
                        rationale=(
                            "The scheduler tried to complete, but some assigned Agents are still running."
                        ),
                        fallback_reason="complete_guard_inflight_agents",
                    )
                ready_targets = self._ready_plan_targets()
                if ready_targets:
                    return SchedulingDecision(
                        decision_type="parallel" if len(ready_targets) > 1 else "assign",
                        action="assign",
                        target_agent_id=ready_targets[0],
                        target_agent_ids=ready_targets,
                        task=self.current_task,
                        task_description=self.current_task,
                        rationale=(
                            "The scheduler tried to complete, but the next collaboration "
                            "stage still needs to run after upstream outputs are available."
                        ),
                        expected_outputs=[
                            "Downstream Agents should consume upstream outputs before reporting.",
                            "Reports are written back to the Blackboard before completion.",
                        ],
                        fallback_reason="complete_guard_ready_stage",
                    )
                return SchedulingDecision(
                    decision_type="parallel" if len(pending) > 1 else "assign",
                    action="assign",
                    target_agent_id=pending[0],
                    target_agent_ids=pending,
                    task=self.current_task,
                    task_description=self.current_task,
                    rationale=(
                        "The scheduler tried to complete, but this is a multi-agent task and "
                        "some requested members have not produced reports yet."
                    ),
                    expected_outputs=[
                        "Each assigned Agent should produce a visible contribution.",
                        "Reports are written back to the Blackboard before completion.",
                    ],
                    fallback_reason="complete_guard_pending_agents",
                )
        return decision

    def _planned_agent_ids(self) -> list[str]:
        return self._valid_target_ids([
            str(item.get("agent_id") or "")
            for item in self._turn_plan
            if isinstance(item, dict)
        ])

    def _ready_plan_targets(self) -> list[str]:
        ready: list[tuple[int, int, str]] = []
        for index, item in enumerate(self._turn_plan):
            if not isinstance(item, dict):
                continue
            agent_id = str(item.get("agent_id") or "")
            if not agent_id or agent_id in self._inflight_agent_ids:
                continue
            if self._agent_has_terminal_report(agent_id):
                continue
            depends_on = [
                str(dep)
                for dep in item.get("depends_on") or []
                if str(dep or "").strip()
            ]
            if not all(self._agent_has_terminal_report(dep) for dep in depends_on):
                continue
            ready.append((int(item.get("stage") or 1), index, agent_id))
        if not ready:
            return []
        next_stage = min(stage for stage, _index, _agent_id in ready)
        return [
            agent_id
            for stage, _index, agent_id in ready
            if stage == next_stage
        ]

    def _agent_has_terminal_report(self, agent_id: str) -> bool:
        report = self.reports.get(agent_id)
        return bool(report and report.state in {AgentState.COMPLETED, AgentState.FAILED})

    def _valid_target_ids(self, ids: list[str] | tuple[str, ...] | None) -> list[str]:
        return [
            agent_id
            for agent_id in dict.fromkeys(str(item) for item in (ids or []) if item)
            if agent_id in self.agents and agent_id != self.scheduler_id
        ]

    def _schedulable_agent_ids(self) -> list[str]:
        return [
            agent_id
            for agent_id, config in self.agents.items()
            if agent_id != self.scheduler_id and config.role != "leader"
        ]

    def _ready_or_idle_agent_ids(self, reports: list[AgentReport]) -> list[str]:
        return [
            report.agent_id
            for report in reports
            if report.agent_id in self.agents
            and report.agent_id != self.scheduler_id
            and report.state in {AgentState.READY, AgentState.IDLE, AgentState.UNKNOWN}
        ]

    def _agent_ids_mentioned_in(self, text: str) -> list[str]:
        lowered = (text or "").lower()
        matched: list[str] = []
        generic_tokens = {
            "agent",
            "assistant",
            "worker",
            "scheduler",
            "master",
            "leader",
            "team",
            "daily",
            "chat",
        }
        for agent_id, config in self.agents.items():
            if agent_id == self.scheduler_id or config.role == "leader":
                continue
            name = (config.name or "").lower()
            role = (config.role or "").lower()
            tokens = {name, agent_id.lower()}
            if role and role not in generic_tokens:
                tokens.add(role)
            tokens.update(
                part
                for part in (part.strip().lower() for part in name.replace("-", " ").split())
                if len(part) >= 3 and part not in generic_tokens
            )
            if any(token and token in lowered for token in tokens):
                matched.append(agent_id)
        return self._valid_target_ids(matched)

    def _requires_multi_agent_turn(
        self,
        named_targets: list[str],
        text: str | None = None,
    ) -> bool:
        if len(named_targets) > 1:
            return True
        task = self.current_task if text is None else text
        if self._looks_like_fullstack_delivery(task):
            return True
        if len(named_targets) == 1 and not self._looks_like_multi_agent_task(task):
            return False
        return self._should_default_collaborative_turn(task) or self._looks_like_multi_agent_task(task)

    def _should_default_collaborative_turn(self, text: str) -> bool:
        if _is_simple_greeting_utf8(text):
            return False
        return len(self._schedulable_agent_ids()) > 2 and self._looks_like_complex_task(text)

    def _looks_like_fullstack_delivery(self, text: str) -> bool:
        normalized = str(text or "").lower()
        if not normalized.strip():
            return False
        fullstack_markers = (
            "前后端",
            "前端后端",
            "前端和后端",
            "后端和前端",
            "fullstack",
            "full-stack",
            "frontend backend",
            "backend frontend",
            "front end back end",
            "五子棋",
            "gomoku",
            "gobang",
            "项目",
            "project",
        )
        doc_markers = (
            "pdf",
            "说明文档",
            "项目说明",
            "说明书",
            "文档",
            "documentation",
            "readme",
        )
        return any(marker in normalized for marker in fullstack_markers) and any(
            marker in normalized for marker in doc_markers
        )

    def _looks_like_complex_task(self, text: str) -> bool:
        normalized = str(text or "").lower()
        if _is_simple_greeting_utf8(normalized):
            return False
        if self._looks_like_fullstack_delivery(normalized):
            return True
        complex_markers = (
            "mvp",
            "端到端",
            "闭环",
            "复杂",
            "多步",
            "方案",
            "准备包",
            "交付",
            "最终成品",
            "产物",
            "复核",
            "验收",
            "部署",
            "发布",
            "风险",
            "链路",
            "校验",
            "归集",
            "多源",
            "html",
            "文档",
            "可下载",
            "可预览",
            "end-to-end",
            "deliverable",
            "artifact",
            "review",
            "deploy",
            "release",
        )
        return any(keyword in normalized for keyword in complex_markers)

    def _is_collaboration_request(self, text: str) -> bool:
        normalized = str(text or "").lower()
        return any(
            keyword in normalized
            for keyword in (
                "组织",
                "协作",
                "协同",
                "多智能体",
                "多个 agent",
                "多个agent",
                "群里",
                "这四个智能体",
                "分工",
                "multi-agent",
                "collaborate",
                "collaboration",
            )
        )

    def _looks_like_multi_agent_task(self, text: str) -> bool:
        normalized = (text or "").lower()
        if _is_simple_greeting_utf8(normalized):
            return False
        if self._looks_like_fullstack_delivery(normalized):
            return True
        explicit_keywords = (
            "multi-agent",
            "multi agent",
            "multiple agents",
            "collaborate",
            "collaboration",
            "parallel",
            "split the work",
            "divide the work",
            "frontend and backend",
            "backend and frontend",
            "full-stack",
            "end-to-end",
            "全栈",
            "前后端",
            "多智能体",
            "多个 agent",
            "多个agent",
            "协作",
            "协同",
            "分工",
            "各自",
            "分别",
            "并行",
        )
        keywords = (
            "多智能体",
            "多agent",
            "多 agent",
            "协作",
            "协同",
            "分工",
            "各自角色",
            "各自",
            "分别",
            "并行",
            "frontend",
            "backend",
            "deploy",
            "reviewer",
            "前端",
            "网页",
            "页面",
            "html",
            "后端",
            "部署",
            "审查",
            "验收",
            "测试方案",
        )
        return self._looks_like_complex_task(normalized) and any(
            keyword in normalized for keyword in (*explicit_keywords, *keywords)
        )

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


def _is_simple_greeting_utf8(text: str) -> bool:
    normalized = (text or "").strip().lower()
    if not normalized:
        return False
    compact = "".join(
        char for char in normalized if char.isalnum() or "\u4e00" <= char <= "\u9fff"
    )
    greetings = {
        "hi",
        "hello",
        "hey",
        "你好",
        "你们好",
        "大家好",
        "早上好",
        "下午好",
        "晚上好",
    }
    return compact in greetings or compact.rstrip("呀啊哈呢哦") in greetings


def _append_reason(base: str, extra: str) -> str:
    if not base:
        return extra
    if extra in base:
        return base
    return f"{base} {extra}"


def _clip_text(text: str, limit: int) -> str:
    normalized = str(text or "").strip()
    if len(normalized) <= limit:
        return normalized
    return normalized[: max(0, limit - 3)].rstrip() + "..."


def _clean_role_label(text: str) -> str:
    normalized = " ".join(str(text or "").replace("_", " ").replace("-", " ").split()).strip()
    if not normalized:
        return ""
    lowered = normalized.lower()
    generic = {
        "agent",
        "assistant",
        "worker",
        "team leader",
        "leader",
        "daily chat agent",
        "chat",
        "default",
    }
    if lowered in generic:
        return ""
    for token in (" agent", " worker", " assistant"):
        if lowered.endswith(token):
            normalized = normalized[: -len(token)].strip()
            break
    return normalized[:24]


def _artifact_reference(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    nested = value.get("artifact") if isinstance(value.get("artifact"), dict) else {}
    artifact_id = (
        value.get("artifact_id")
        or value.get("id")
        or nested.get("artifact_id")
        or nested.get("id")
    )
    reference = {
        "artifact_id": artifact_id,
        "artifact_type": value.get("artifact_type") or value.get("type") or nested.get("artifact_type") or nested.get("type"),
        "preview_message_id": value.get("preview_message_id") or nested.get("preview_message_id"),
        "file_id": value.get("file_id") or nested.get("file_id"),
        "filename": value.get("filename") or nested.get("filename"),
        "title": value.get("title") or value.get("name") or nested.get("title") or nested.get("name"),
        "format": value.get("format") or nested.get("format"),
        "media_type": value.get("media_type") or nested.get("media_type"),
        "preview_url": value.get("preview_url") or value.get("storage_url") or nested.get("preview_url") or nested.get("storage_url"),
        "export_url": value.get("export_url") or nested.get("export_url"),
        "public_url": value.get("public_url") or nested.get("public_url"),
        "download_url": value.get("download_url") or nested.get("download_url"),
    }
    if not any(
        reference.get(key)
        for key in (
            "artifact_id",
            "preview_message_id",
            "file_id",
            "filename",
            "title",
            "preview_url",
            "export_url",
            "public_url",
            "download_url",
        )
    ):
        return {}
    return {key: item for key, item in reference.items() if item}


def _tool_result_candidates(result: dict[str, Any]) -> list[Any]:
    candidates: list[Any] = [result]
    for key in ("output", "result"):
        value = result.get(key)
        if isinstance(value, dict):
            candidates.append(value)
            nested_output = value.get("output")
            if isinstance(nested_output, dict):
                candidates.append(nested_output)
            nested_artifact = value.get("artifact")
            if isinstance(nested_artifact, dict):
                candidates.append(nested_artifact)
    return candidates


def _first_ready_agent_id(reports: list[AgentReport], scheduler_id: str) -> str | None:
    for report in reports:
        if report.agent_id == scheduler_id:
            continue
        if report.state in {AgentState.READY, AgentState.IDLE, AgentState.UNKNOWN}:
            return report.agent_id
    return None


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


def _dict_payload(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _mention_target_ids_from_metadata(value: Any) -> list[str]:
    metadata = _dict_payload(value)
    targets: list[str] = []
    raw_targets = metadata.get("mention_target_agent_ids")
    if isinstance(raw_targets, list):
        for item in raw_targets:
            agent_id = str(item or "").strip()
            if agent_id and agent_id not in targets:
                targets.append(agent_id)
    raw_mentions = metadata.get("agent_mentions")
    if isinstance(raw_mentions, list):
        for item in raw_mentions:
            if not isinstance(item, dict):
                continue
            agent_id = str(item.get("agent_id") or item.get("id") or "").strip()
            if agent_id and agent_id not in targets:
                targets.append(agent_id)
    return targets


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
