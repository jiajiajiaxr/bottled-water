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
    CONTROL_CANCEL,
    CONTROL_COMPLETE,
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
        self.scheduler = SchedulerAgent(
            session_id=session_id,
            agents=agents,
            event_bus=self.event_bus,
            blackboard_mgr=self.blackboard_mgr,
            model_provider=model_provider,
        )
        self._event_queue: asyncio.Queue[Event] = asyncio.Queue()
        self._observer_subscription = self.event_bus.subscribe(None, self._event_queue.put, target="*")
        self._running = False

    async def run(self, user_message: str) -> AsyncIterator[Event]:
        self._running = True
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
                timeout = max(0.01, deadline - asyncio.get_running_loop().time())
                try:
                    event = await asyncio.wait_for(self._event_queue.get(), timeout=timeout)
                except asyncio.TimeoutError:
                    break
                yield event
                if event.type == CONTROL_COMPLETE:
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
            await self.event_bus.publish(final_event)
            yield final_event
        finally:
            await self._stop_actors()
            self.event_bus.unsubscribe(self._observer_subscription)
            self._running = False

    async def handle_user_input(self, content: str) -> AsyncIterator[Event]:
        async for event in self.run(content):
            yield event

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
            "running": self._running,
            "agents": {
                agent_id: {"state": actor.state.value}
                for agent_id, actor in self.actors.items()
            },
        }

    def _start_actors(self) -> None:
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
                use_streaming=False,
            )
            self.actors[agent_id] = actor
            actor.start()

    def _mention_targets(self, user_message: str) -> list[str]:
        if not user_message or re.search(r"@(全员|所有人|大家)|全员|所有 Agent|协作", user_message, re.I):
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

    async def _stop_actors(self) -> None:
        await self.scheduler.stop()
        await asyncio.gather(*(actor.stop() for actor in self.actors.values()), return_exceptions=True)
        self.actors.clear()
