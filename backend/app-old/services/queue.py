from __future__ import annotations

import json
from typing import Any

import redis.asyncio as redis

from app.core.config import get_settings


class QueueService:
    """Redis Streams + Sorted Set queue with in-memory fallback for local tests."""

    def __init__(self) -> None:
        self._memory: list[dict[str, Any]] = []
        self._redis: redis.Redis | None = None
        self._redis_checked = False

    async def _client(self) -> redis.Redis | None:
        if self._redis_checked:
            return self._redis
        self._redis_checked = True
        if self._redis is not None:
            return self._redis
        try:
            client = redis.from_url(
                get_settings().redis_url,
                decode_responses=True,
                socket_connect_timeout=0.25,
                socket_timeout=0.5,
            )
            await client.ping()
            self._redis = client
            return self._redis
        except Exception:
            return None

    async def enqueue(self, task: dict[str, Any], priority: int = 50) -> None:
        client = await self._client()
        if client is None:
            self._memory.append(task)
            return
        encoded = json.dumps(task, ensure_ascii=False)
        await client.xadd("agenthub:tasks", {"payload": encoded})
        await client.zadd("agenthub:task-priority", {task["id"]: priority})

    async def memory_items(self) -> list[dict[str, Any]]:
        return list(self._memory)


queue_service = QueueService()
