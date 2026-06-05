import asyncio

import pytest

from agent_runtime.core.types import Event
from agent_runtime.runtime.event_dispatcher import EventDispatcher


@pytest.mark.asyncio
async def test_eventbus_broadcast_and_target_routing():
    bus = EventDispatcher()
    broadcast: list[Event] = []
    target_a: list[Event] = []
    target_b: list[Event] = []
    observer: list[Event] = []

    bus.subscribe("agent.*", lambda event: _append(broadcast, event), target=None)
    bus.subscribe("control.*", lambda event: _append(target_a, event), target="agent_a")
    bus.subscribe("control.*", lambda event: _append(target_b, event), target="agent_b")
    bus.subscribe("*", lambda event: _append(observer, event), target="*")

    await bus.publish(Event(type="agent.report", payload={"ok": True}, source="agent:a"))
    await bus.publish(
        Event(type="control.assign", payload={"task": "do it"}, source="scheduler", target="agent_a")
    )
    await asyncio.sleep(0)

    assert [event.type for event in broadcast] == ["agent.report"]
    assert [event.type for event in target_a] == ["control.assign"]
    assert target_b == []
    assert [event.type for event in observer] == ["agent.report", "control.assign"]


async def _append(target: list[Event], event: Event) -> None:
    target.append(event)
