from __future__ import annotations

from collections.abc import AsyncIterator

from app.services.realtime.event_bus import Event, event_bus


def conversation_channel(conversation_id: str) -> str:
    return f"conversation:{conversation_id}"


async def subscribe_conversation(conversation_id: str, *, replay: bool = True) -> AsyncIterator[Event]:
    async for event in event_bus.subscribe(conversation_channel(conversation_id), replay=replay):
        yield event
