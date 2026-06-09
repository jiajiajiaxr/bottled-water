from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from common.logger import get_logger
from model_provider.core.config import ModelConfig
from model_provider.core.interfaces import BaseModelProvider, ChatMessage
from model_provider.core.streaming import collect_chat_stream
from model_provider.factory import create_provider

from ..core.types import AgentConfig, AgentReport, AgentState, SchedulingDecision
from .base import Scheduler

logger = get_logger(__name__)


class TechLeadScheduler(Scheduler):
    """LLM-backed scheduler with deterministic fallbacks."""

    SYSTEM_PROMPT = """You are the Team Leader Agent for an AgentHub multi-agent conversation.

Choose exactly one next scheduling action based on the user task, available agents,
the current turn plan, blackboard summary, and current agent reports.

You are a real scheduler, not a hidden super-agent. You can only assign current
conversation members. Prefer the smallest useful set of agents, and respect
dependencies:
- If the task asks for a full-stack app/project with backend data/API/storage,
  assign backend/service work first. Frontend should wait for backend output
  before implementing UI/API integration.
- If the task also asks for PDF/Word/documentation, documentation should be
  produced after implementation outputs are available.
- If the task asks for deployment/release, deploy after implementation and review.
- Independent subtasks can be parallel, but dependent subtasks must be staged.
- For greetings or broad chat, assign only the most suitable chat agent.
- If the current turn plan contains queued stages, follow that plan unless a
  report says a dependency failed or the user explicitly changed direction.

Return JSON only, with these fields:
{{
  "decision_type": "assign|parallel|wait|complete|escalate|user_input",
  "target_agent_id": "agent id or null",
  "target_agent_ids": ["agent id"],
  "task_description": "short task for the target agent",
  "rationale": "why this decision is appropriate",
  "requires_verification": false,
  "verification_agents": []
}}

Available agents:
{agent_profiles}

Blackboard:
{blackboard_summary}

Agent reports:
{agent_reports}
"""

    def __init__(
        self,
        agents: Dict[str, AgentConfig] | None = None,
        model_provider: Optional[BaseModelProvider] = None,
        model_config: Optional[ModelConfig] = None,
    ):
        super().__init__(agents or {})
        self.model_provider = model_provider
        if model_provider is None and model_config is not None:
            self.model_provider = create_provider(model_config)

    async def make_decision(
        self,
        blackboard: Dict[str, Any],
        agent_reports: List[AgentReport],
        conversation_context: Dict[str, Any],
    ) -> SchedulingDecision:
        if self.model_provider is None:
            logger.warning("TechLeadScheduler has no model provider; using fallback")
            return self._fallback_decision(agent_reports)
        try:
            return await self._llm_decision(blackboard, agent_reports, conversation_context)
        except Exception as exc:
            logger.error("LLM scheduling decision failed", error=str(exc))
            return self._fallback_decision(agent_reports)

    async def _llm_decision(
        self,
        blackboard: Dict[str, Any],
        agent_reports: List[AgentReport],
        conversation_context: Dict[str, Any],
    ) -> SchedulingDecision:
        system_prompt = self.SYSTEM_PROMPT.format(
            agent_profiles=self._build_agent_profiles(),
            blackboard_summary=self._build_blackboard_summary(blackboard),
            agent_reports=self._build_reports_text(agent_reports),
        )
        user_prompt = json.dumps(
            {
                "round": conversation_context.get("round", 0),
                "session_id": conversation_context.get("session_id", "unknown"),
                "current_task": conversation_context.get("current_task", ""),
                "agent_count": conversation_context.get("agent_count", len(self.agents)),
                "turn_plan": conversation_context.get("turn_plan") or [],
                "scheduler_policy": {
                    "respect_plan_dependencies": True,
                    "backend_before_frontend_for_data_apps": True,
                    "documentation_last": True,
                    "deploy_after_implementation": True,
                },
            },
            ensure_ascii=False,
        )
        logger.info("LLM scheduler decision requested", round=conversation_context.get("round"))
        response = await collect_chat_stream(
            self.model_provider,
            messages=[ChatMessage(role="user", content=user_prompt)],
            system_prompt=system_prompt,
            temperature=0.3,
        )
        decision_data = self._parse_decision_json(response.content)
        logger.info(
            "LLM scheduler decision completed",
            decision=decision_data.get("decision_type"),
            target=decision_data.get("target_agent_id"),
        )
        return SchedulingDecision(
            decision_type=str(decision_data.get("decision_type") or "wait"),
            target_agent_id=decision_data.get("target_agent_id"),
            target_agent_ids=_string_list(decision_data.get("target_agent_ids")),
            task_description=str(decision_data.get("task_description") or ""),
            rationale=str(decision_data.get("rationale") or ""),
            requires_verification=bool(decision_data.get("requires_verification")),
            verification_agents=_string_list(decision_data.get("verification_agents")),
        )

    def _parse_decision_json(self, content: str) -> Dict[str, Any]:
        text = (content or "").strip()
        if not text:
            return {"decision_type": "wait", "rationale": "empty model response"}
        try:
            value = json.loads(text)
            return value if isinstance(value, dict) else {"decision_type": "wait"}
        except json.JSONDecodeError:
            pass
        for pattern in (r"```json\s*(.*?)\s*```", r"```\s*(.*?)\s*```", r"\{[\s\S]*\}"):
            match = re.search(pattern, text, re.DOTALL)
            if not match:
                continue
            candidate = match.group(1) if match.lastindex else match.group(0)
            try:
                value = json.loads(candidate.strip())
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                return value
        logger.warning("Could not parse scheduler decision JSON", content=text[:200])
        return {"decision_type": "wait", "rationale": "无法解析: could not parse model response"}

    def _fallback_decision(self, agent_reports: List[AgentReport]) -> SchedulingDecision:
        ready_reports = [report for report in agent_reports if report.state == AgentState.READY]
        if len(ready_reports) > 2:
            targets = [report.agent_id for report in ready_reports]
            return SchedulingDecision(
                decision_type="parallel",
                target_agent_id=targets[0],
                target_agent_ids=targets,
                task_description="Execute the current task with each Agent contributing its relevant specialty.",
                rationale="回退策略: group chat has more than two ready agents, organize them in parallel.",
            )
        for report in agent_reports:
            if report.state == AgentState.READY:
                return SchedulingDecision(
                    decision_type="assign",
                    target_agent_id=report.agent_id,
                    task_description="Execute the current task",
                    rationale="回退策略: first ready agent",
                )
        if agent_reports and all(report.state == AgentState.COMPLETED for report in agent_reports):
            return SchedulingDecision(decision_type="complete", rationale="all agents completed")
        return SchedulingDecision(decision_type="wait", rationale="fallback: no ready agent")

    def _build_agent_profiles(self) -> str:
        lines: list[str] = []
        for agent_id, agent in self.agents.items():
            lines.append(
                json.dumps(
                    {
                        "id": agent_id,
                        "name": agent.name,
                        "role": agent.role,
                        "tools": agent.tools,
                        "system_prompt": (agent.system_prompt or "")[:500],
                    },
                    ensure_ascii=False,
                )
            )
        return "\n".join(lines) or "No agents"

    def _build_blackboard_summary(self, blackboard: Dict[str, Any]) -> str:
        if not blackboard:
            return "Empty"
        summary = {
            "recent_history": blackboard.get("recent_history") or blackboard.get("history") or [],
            "summaries": blackboard.get("summaries") or [],
            "kv_state": blackboard.get("kv_state") or blackboard.get("state") or {},
        }
        return json.dumps(summary, ensure_ascii=False, default=str)[:4000]

    def _build_reports_text(self, reports: List[AgentReport]) -> str:
        if not reports:
            return "No reports"
        lines: list[str] = []
        for report in reports:
            lines.append(
                json.dumps(
                    {
                        "agent_id": report.agent_id,
                        "state": report.state.value if hasattr(report.state, "value") else str(report.state),
                        "will": report.will.value if hasattr(report.will, "value") else str(report.will),
                        "target_task": report.target_task,
                        "blockers": report.blockers,
                        "confidence": report.confidence,
                        "rationale": report.rationale,
                    },
                    ensure_ascii=False,
                )
            )
        return "\n".join(lines)

    async def resolve_conflict(
        self,
        conflict_type: str,
        conflicting_reports: List[AgentReport],
        blackboard: Dict[str, Any],
    ) -> SchedulingDecision:
        if not conflicting_reports:
            return SchedulingDecision(decision_type="wait", rationale="no conflicting reports")
        if self.model_provider is None:
            return SchedulingDecision(
                decision_type="assign",
                target_agent_id=conflicting_reports[0].agent_id,
                rationale="fallback: first conflicting agent",
            )
        try:
            prompt = json.dumps(
                {
                    "conflict_type": conflict_type,
                    "reports": [report.__dict__ for report in conflicting_reports],
                    "blackboard": blackboard,
                },
                ensure_ascii=False,
                default=str,
            )
            response = await collect_chat_stream(
                self.model_provider,
                messages=[ChatMessage(role="user", content=prompt)],
                system_prompt='Resolve the conflict and return JSON: {"target_agent_id": "...", "rationale": "..."}',
                temperature=0.3,
            )
            data = self._parse_decision_json(response.content)
            return SchedulingDecision(
                decision_type="assign",
                target_agent_id=data.get("target_agent_id") or conflicting_reports[0].agent_id,
                rationale=str(data.get("rationale") or "LLM conflict resolution"),
            )
        except Exception as exc:
            logger.error("LLM conflict resolution failed", error=str(exc))
            return SchedulingDecision(
                decision_type="assign",
                target_agent_id=conflicting_reports[0].agent_id,
                rationale="fallback: conflict resolution failed",
            )


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item or "").strip()]
