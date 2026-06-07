"""Event-driven Actor Orchestrator.

This is the async-runtime path requested by the V2 design docs. The legacy
round-based Orchestrator remains available; callers opt in with
``scheduler_config.runtime == "actor"``.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import AsyncIterator
from typing import Any

from model_provider.core.interfaces import BaseModelProvider

from common.logger import get_logger
from ..context.agent_ctx import AgentContextManager
from ..context.blackboard import BlackboardManager
from ..core.interfaces import PersistenceBackend, ToolExecutor
from ..core.protocol import (
    AGENT_REPORT,
    CONTROL_CANCEL,
    CONTROL_ASSIGN,
    CONTROL_COMPLETE,
    SCHEDULER_DECISION,
    SYSTEM_SESSION_CANCELLED,
    SYSTEM_SESSION_COMPLETED,
    SYSTEM_SESSION_STARTED,
    USER_INPUT,
)
from ..core.types import AgentConfig, Event
from ..strategies.scheduler_agent import SchedulerAgent
from .agent_actor import AgentActor
from .event_dispatcher import EventDispatcher

logger = get_logger(__name__)


class ActorOrchestrator:
    """Lifecycle manager for event-driven Agent actors."""

    def __init__(
        self,
        *,
        session_id: str,
        agents: dict[str, AgentConfig],
        model_provider: BaseModelProvider,
        persistence: PersistenceBackend | None = None,
        tool_executor: ToolExecutor | None = None,
        max_runtime_seconds: float = 120.0,
    ) -> None:
        self.session_id = session_id
        self.agents = agents
        self.model_provider = model_provider
        self.persistence = persistence
        self.tool_executor = tool_executor
        self.max_runtime_seconds = max_runtime_seconds
        self.event_bus = EventDispatcher()
        self.blackboard_mgr = BlackboardManager(persistence=persistence, event_bus=self.event_bus)
        self.agent_context_mgr = AgentContextManager()
        self.actors: dict[str, AgentActor] = {}
        self.scheduler: SchedulerAgent | None = None
        self._event_queue: asyncio.Queue[Event] = asyncio.Queue()
        self._observer_subscription: str | None = self.event_bus.subscribe(None, self._event_queue.put, target="*")
        self._pending_user_inputs: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._running = False

    async def run(self, user_message: str) -> AsyncIterator[Event]:
        self._ensure_observer_subscription()
        self._running = True
        self._pending_user_inputs = asyncio.Queue()
        await self.blackboard_mgr.create(self.session_id)
        await self.blackboard_mgr.append_history(
            self.session_id,
            {"type": "user_input", "content": user_message},
        )
        self._start_actors()
        await self.event_bus.publish(
            Event(
                type=SYSTEM_SESSION_STARTED,
                payload={"session_id": self.session_id, "runtime": "actor"},
                source="orchestrator",
                channel="all",
            )
        )
        if self._is_simple_greeting(user_message):
            await self._publish_direct_greeting(user_message)
        else:
            await self.event_bus.publish(
                Event(
                    type=USER_INPUT,
                    payload={
                        "session_id": self.session_id,
                        "content": user_message,
                        "mention_target_agent_ids": self._mention_targets(user_message),
                    },
                    source="user",
                    channel="all",
                )
            )

        deadline = asyncio.get_running_loop().time() + self.max_runtime_seconds
        completed = False
        try:
            while asyncio.get_running_loop().time() < deadline:
                await self._dispatch_pending_user_inputs()
                timeout = max(0.01, deadline - asyncio.get_running_loop().time())
                try:
                    event = await asyncio.wait_for(self._event_queue.get(), timeout=timeout)
                except asyncio.TimeoutError:
                    break
                if event.type == "internal.user_input_pending":
                    await self._dispatch_pending_user_inputs()
                    continue
                yield event
                if event.type == CONTROL_COMPLETE:
                    if not self._pending_user_inputs.empty():
                        await self._dispatch_pending_user_inputs()
                        continue
                    completed = True
                    break
            final_event = Event(
                type=SYSTEM_SESSION_COMPLETED if completed else SYSTEM_SESSION_CANCELLED,
                payload={
                    "session_id": self.session_id,
                    "runtime": "actor",
                    "reason": "completed" if completed else "timeout",
                },
                source="orchestrator",
                channel="all",
            )
            self._running = False
            await self.event_bus.publish(final_event)
            yield final_event
        finally:
            await self._stop_actors()
            if self._observer_subscription:
                self.event_bus.unsubscribe(self._observer_subscription)
                self._observer_subscription = None
            self._running = False

    async def handle_user_input(self, content: str) -> AsyncIterator[Event]:
        if not self._running:
            async for event in self.run(content):
                yield event
            return

        await self.blackboard_mgr.append_history(
            self.session_id,
            {"type": "user_input", "content": content, "interrupt": True},
        )
        await self._pending_user_inputs.put(
            {
                "content": content,
                "mention_target_agent_ids": self._mention_targets(content),
            }
        )
        yield Event(
            type="user.input_queued",
            payload={"session_id": self.session_id, "content": content},
            source="user",
            channel="all",
        )
        await self._event_queue.put(
            Event(
                type="internal.user_input_pending",
                payload={"session_id": self.session_id},
                source="system",
                channel="internal",
            )
        )

    async def cancel(self, reason: str = "user_cancelled") -> None:
        for agent_id in list(self.actors):
            await self.event_bus.publish(
                Event(
                    type=CONTROL_CANCEL,
                    payload={"reason": reason, "session_id": self.session_id},
                    source="orchestrator",
                    target=agent_id,
                    channel="internal",
                )
            )
        await self.event_bus.publish(
            Event(
                type=SYSTEM_SESSION_CANCELLED,
                payload={"session_id": self.session_id, "runtime": "actor", "reason": reason},
                source="orchestrator",
                channel="all",
            )
        )
        await self._stop_actors()

    def get_status(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "runtime": "actor",
            "status": "running" if self._running else "idle",
            "running": self._running,
            "agents": {
                agent_id: {"state": actor.state.value}
                for agent_id, actor in self.actors.items()
            },
        }

    def _ensure_observer_subscription(self) -> None:
        if self._observer_subscription is None:
            self._event_queue = asyncio.Queue()
            self._observer_subscription = self.event_bus.subscribe(None, self._event_queue.put, target="*")
        if not hasattr(self, "_pending_user_inputs") or self._pending_user_inputs is None:
            self._pending_user_inputs = asyncio.Queue()

    def _start_actors(self) -> None:
        self.scheduler = SchedulerAgent(
            session_id=self.session_id,
            agents=self.agents,
            event_bus=self.event_bus,
            blackboard_mgr=self.blackboard_mgr,
            model_provider=self.model_provider,
        )
        self.scheduler.start()
        for agent_id, config in self.agents.items():
            actor = AgentActor(
                session_id=self.session_id,
                agent_config=config,
                model_provider=self.model_provider,
                event_bus=self.event_bus,
                tool_executor=self.tool_executor,
                blackboard_mgr=self.blackboard_mgr,
                agent_context_mgr=self.agent_context_mgr,
                use_streaming=True,
            )
            self.actors[agent_id] = actor
            actor.start()

    def _mention_targets(self, user_message: str) -> list[str]:
        if not user_message or re.search(r"@(全员|所有人|大家)|全员|所有\s*Agent|协作", user_message, re.I):
            return []
        targets: list[str] = []
        lowered = user_message.lower()
        for agent_id, config in self.agents.items():
            name = (config.name or "").strip()
            if not name:
                continue
            patterns = {
                f"@{name}",
                f"＠{name}",
                f"@{name.lower()}",
            }
            if any(pattern.lower() in lowered for pattern in patterns):
                targets.append(agent_id)
        return list(dict.fromkeys(targets))

    async def _dispatch_pending_user_inputs(self) -> None:
        while not self._pending_user_inputs.empty():
            payload = await self._pending_user_inputs.get()
            await self.event_bus.publish(
                Event(
                    type=USER_INPUT,
                    payload={
                        "session_id": self.session_id,
                        "content": str(payload.get("content") or ""),
                        "mention_target_agent_ids": payload.get("mention_target_agent_ids") or [],
                        "interrupt": True,
                    },
                    source="user",
                    channel="all",
                )
            )

    async def _stop_actors(self) -> None:
        if self.scheduler is not None:
            await self.scheduler.stop()
            self.scheduler = None
        await asyncio.gather(*(actor.stop() for actor in self.actors.values()), return_exceptions=True)
        self.actors.clear()

    async def _publish_direct_greeting(self, user_message: str) -> None:
        target_id, target = self._chat_agent()
        if not target_id or target is None:
            await self.event_bus.publish(
                Event(
                    type=CONTROL_COMPLETE,
                    payload={"reason": "simple greeting without available agent"},
                    source="orchestrator",
                    channel="all",
                )
            )
            return
        reply = (
            "你好呀，我在。你可以直接告诉我需要生成文档、处理文件、运行工具，"
            "或者让多个 Agent 协作完成一个任务。"
        )
        decision = {
            "action": "assign",
            "target_agent_ids": [target_id],
            "task": user_message,
            "expected_outputs": ["简洁问候回复"],
            "requires_review": False,
            "fallback_reason": "",
            "decision_type": "assign",
            "target_agent_id": target_id,
            "task_description": user_message,
            "rationale": "Simple greeting fast path.",
            "requires_verification": False,
            "verification_agents": [],
        }
        await self.event_bus.publish(
            Event(
                type=SCHEDULER_DECISION,
                payload={"round": 1, "decision": decision},
                source="scheduler:team_leader",
                channel="all",
            )
        )
        await self.event_bus.publish(
            Event(
                type=CONTROL_ASSIGN,
                payload={
                    "round": 1,
                    "target_agent_id": target_id,
                    "task": user_message,
                    "rationale": "Simple greeting fast path.",
                    "direct": True,
                },
                source="scheduler:team_leader",
                channel="all",
            )
        )
        await self.event_bus.publish(
            Event(
                type=AGENT_REPORT,
                payload={
                    "agent_id": target_id,
                    "task": user_message,
                    "work_product": reply,
                    "report": {
                        "agent_id": target_id,
                        "state": "completed",
                        "will": "complete",
                        "blockers": [],
                        "priority": 1,
                        "confidence": 1.0,
                        "rationale": "Simple greeting completed.",
                    },
                },
                source=f"agent:{target_id}",
                channel="all",
            )
        )
        await self.event_bus.publish(
            Event(
                type=CONTROL_COMPLETE,
                payload={"reason": "simple greeting completed", "round": 1},
                source="scheduler:team_leader",
                channel="all",
            )
        )

    def _chat_agent(self) -> tuple[str | None, AgentConfig | None]:
        for agent_id, config in self.agents.items():
            text = f"{config.name} {config.role}".lower()
            if "daily chat" in text or "chat" in text or "日常" in text:
                return agent_id, config
        for agent_id, config in self.agents.items():
            return agent_id, config
        return None, None

    @staticmethod
    def _is_simple_greeting(text: str) -> bool:
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
