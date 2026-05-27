from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import redis.asyncio as redis

from app.core.config import get_settings


def event_timestamp() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


@dataclass
class Event:
    event: str
    data: dict[str, Any]
    timestamp: str

    def as_dict(self) -> dict[str, Any]:
        return {"event": self.event, "data": self.data, "timestamp": self.timestamp}

    def as_sse(self) -> dict[str, Any]:
        return {"event": self.event, "data": json.dumps(self.data, ensure_ascii=False)}


class EventBus:
    def __init__(self) -> None:
        self._queues: dict[str, set[asyncio.Queue[Event]]] = defaultdict(set)
        self._history: dict[str, list[Event]] = defaultdict(list)
        self._redis: redis.Redis | None = None
        self._redis_checked = False

    async def _get_redis(self) -> redis.Redis | None:
        if self._redis_checked:
            return self._redis
        self._redis_checked = True
        try:
            client = redis.from_url(
                get_settings().redis_url,
                decode_responses=True,
                socket_connect_timeout=0.25,
                socket_timeout=0.5,
            )
            await client.ping()
            self._redis = client
        except Exception:
            self._redis = None
        return self._redis

    async def publish(self, channel: str, event: str, data: dict[str, Any]) -> None:
        payload = Event(event=event, data=data, timestamp=event_timestamp())
        self._history[channel].append(payload)
        if len(self._history[channel]) > 200:
            self._history[channel] = self._history[channel][-200:]
        for queue in list(self._queues[channel]):
            queue.put_nowait(payload)
        client = await self._get_redis()
        if client is not None:
            encoded = json.dumps(payload.as_dict(), ensure_ascii=False)
            await client.publish(channel, encoded)
            await client.xadd(f"stream:{channel}", {"payload": encoded}, maxlen=500, approximate=True)

    async def subscribe(self, channel: str, replay: bool = True) -> AsyncIterator[Event]:
        queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=500)
        if replay:
            for event in self._history[channel][-50:]:
                queue.put_nowait(event)
        self._queues[channel].add(queue)
        try:
            while True:
                event = await queue.get()
                yield event
        finally:
            self._queues[channel].discard(queue)


event_bus = EventBus()
