import asyncio

import pytest

from agent_runtime.context.blackboard import BlackboardManager
from agent_runtime.core.protocol import CONTROL_ASSIGN, SCHEDULER_DECISION, USER_INPUT
from agent_runtime.core.types import AgentConfig, Event
from agent_runtime.runtime.agent_loop import AgentLoop
from agent_runtime.runtime.agent_actor import AgentActor
from agent_runtime.runtime.event_dispatcher import EventDispatcher
from agent_runtime.strategies.scheduler_agent import SchedulerAgent
from model_provider.core.interfaces import ChatResponse


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


@pytest.mark.asyncio
async def test_agent_loop_forces_artifact_tool_when_model_only_returns_text():
    events: list[Event] = []
    executor = FakeToolExecutor()
    loop = AgentLoop(
        AgentConfig(
            id="daily",
            name="Daily Chat Agent",
            system_prompt="You can create artifacts.",
            role="chat",
            tools=["artifact.create_pdf"],
        ),
        FakeModelProvider(),
        use_streaming=False,
    )

    result = await loop.run(
        "生成示例pdf预览卡片",
        {},
        tool_executor=executor,
        emit_event=lambda event: _append(events, event),
    )

    assert executor.calls
    assert executor.calls[0].tool_name == "artifact.create_pdf"
    tool_result = next(event for event in events if event.type == "agent.tool_result")
    assert tool_result.payload["result"]["output"]["artifact_id"] == "artifact-1"
    assert result["work_product"]


async def _append(target: list[Event], event: Event) -> None:
    target.append(event)


async def _wait_for(events: list[Event], event_type: str) -> Event:
    for _ in range(50):
        for event in events:
            if event.type == event_type:
                return event
        await asyncio.sleep(0.02)
    raise AssertionError(f"event {event_type} was not published")


class FakeModelProvider:
    async def chat(self, **_kwargs):
        return ChatResponse(content="li", tool_calls=None)


class FakeToolExecutor:
    def __init__(self) -> None:
        self.calls = []

    async def list_tools(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": "artifact.create_pdf",
                    "description": "Create PDF",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]

    async def execute(self, tool_call):
        self.calls.append(tool_call)
        return {
            "type": "tool",
            "tool_name": tool_call.tool_name,
            "status": "succeeded",
            "output": {
                "artifact_id": "artifact-1",
                "artifact": {"conversationId": "conv-1", "title": "示例 PDF"},
                "preview_message_id": "preview-1",
            },
        }
