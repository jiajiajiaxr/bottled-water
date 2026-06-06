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


@pytest.mark.asyncio
async def test_eventbus_replaces_deduplicated_sink():
    bus = EventDispatcher()
    first: list[Event] = []
    second: list[Event] = []

    bus.register_sink(_ListSink(first, "websocket:conv-1"))
    bus.register_sink(_ListSink(second, "websocket:conv-1"))

    await bus.publish(Event(type="agent.token", payload={"token": "hi"}))

    assert first == []
    assert [event.type for event in second] == ["agent.token"]


class _ListSink:
    def __init__(self, target: list[Event], dedupe_key: str):
        self.target = target
        self.dedupe_key = dedupe_key

    async def emit(self, event: Event) -> None:
        self.target.append(event)

    async def emit_batch(self, events: list[Event]) -> None:
        self.target.extend(events)
