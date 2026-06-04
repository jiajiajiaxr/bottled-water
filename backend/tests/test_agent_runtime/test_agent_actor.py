import asyncio

import pytest
from model_provider import ChatResponse

from agent_runtime.context.blackboard import BlackboardManager
from agent_runtime.core.protocol import AGENT_REPORT, CONTROL_ASSIGN
from agent_runtime.core.types import AgentConfig, AgentState, Event
from agent_runtime.runtime.agent_actor import AgentActor
from agent_runtime.runtime.event_dispatcher import EventDispatcher


@pytest.mark.asyncio
async def test_agent_actor_runs_assignment_and_publishes_report(mock_provider, mock_tool_executor):
    mock_provider.responses = [
        ChatResponse(
            content='done\n```status_report\n{"state": "completed", "will": "complete", "confidence": 0.9}\n```'
        )
    ]
    bus = EventDispatcher()
    blackboard = BlackboardManager(event_bus=bus)
    events: list[Event] = []
    bus.subscribe("*", lambda event: _append(events, event), target="*")
    actor = AgentActor(
        session_id="sess_actor",
        agent_config=AgentConfig(id="coder", name="Coder", system_prompt="You code."),
        model_provider=mock_provider,
        event_bus=bus,
        tool_executor=mock_tool_executor,
        blackboard_mgr=blackboard,
        use_streaming=False,
    )
    actor.start()

    await bus.publish(
        Event(
            type=CONTROL_ASSIGN,
            payload={"task": "write a helper"},
            source="scheduler",
            target="coder",
        )
    )
    report_event = await _wait_for(events, AGENT_REPORT)
    await actor.stop()

    assert report_event.payload["agent_id"] == "coder"
    assert report_event.payload["report"]["state"] == AgentState.COMPLETED.value
    stored = await blackboard.get("sess_actor")
    assert stored is not None
    assert any(item.get("type") == "agent_work" for item in stored["raw_history"])


async def _append(target: list[Event], event: Event) -> None:
    target.append(event)


async def _wait_for(events: list[Event], event_type: str) -> Event:
    for _ in range(50):
        for event in events:
            if event.type == event_type:
                return event
        await asyncio.sleep(0.02)
    raise AssertionError(f"event {event_type} was not published")

