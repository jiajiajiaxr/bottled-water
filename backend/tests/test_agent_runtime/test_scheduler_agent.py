import asyncio

import pytest

from agent_runtime.context.blackboard import BlackboardManager
from agent_runtime.core.protocol import CONTROL_ASSIGN, SCHEDULER_DECISION, USER_INPUT
from agent_runtime.core.types import AgentConfig, Event
from agent_runtime.runtime.agent_actor import AgentActor
from agent_runtime.runtime.event_dispatcher import EventDispatcher
from agent_runtime.strategies.scheduler_agent import SchedulerAgent


@pytest.mark.asyncio
async def test_scheduler_agent_turns_user_input_into_control_assign():
    bus = EventDispatcher()
    blackboard = BlackboardManager(event_bus=bus)
    events: list[Event] = []
    bus.subscribe("*", lambda event: _append(events, event), target="*")
    scheduler = SchedulerAgent(
        session_id="sess_scheduler",
        agents={
            "frontend": AgentConfig(id="frontend", name="Frontend", system_prompt="build ui"),
            "backend": AgentConfig(id="backend", name="Backend", system_prompt="build api"),
        },
        event_bus=bus,
        blackboard_mgr=blackboard,
        model_provider=None,
    )
    scheduler.start()

    assert isinstance(scheduler, AgentActor)

    await bus.publish(Event(type=USER_INPUT, payload={"content": "build a page"}, source="user"))
    decision = await _wait_for(events, SCHEDULER_DECISION)
    assign = await _wait_for(events, CONTROL_ASSIGN)
    await scheduler.stop()

    assert decision.payload["decision"]["decision_type"] == "assign"
    assert assign.target == "frontend"
    stored = await blackboard.get("sess_scheduler")
    assert stored is not None
    assert any(item.get("type") == "scheduler_agent_decision" for item in stored["raw_history"])


async def _append(target: list[Event], event: Event) -> None:
    target.append(event)


async def _wait_for(events: list[Event], event_type: str) -> Event:
    for _ in range(50):
        for event in events:
            if event.type == event_type:
                return event
        await asyncio.sleep(0.02)
    raise AssertionError(f"event {event_type} was not published")
