"""
SSE 事件投递实现

把 agent_runtime 的事件转换为 SSE 流推送给前端。
"""

import asyncio
from typing import Dict, List, Optional

from agent_runtime.core.types import Event
from agent_runtime.core.interfaces import EventSink

from common.logger import get_logger

logger = get_logger(__name__)


class SSEEventSink(EventSink):
    """
    SSE 事件投递器

    每个会话维护一个 asyncio.Queue，API 层从中读取并推送给客户端。
    """

    _queues: Dict[str, asyncio.Queue] = {}

    def __init__(self, conversation_id: str):
        self.conversation_id = conversation_id
        self._queues[conversation_id] = asyncio.Queue()

    async def emit(self, event: Event) -> None:
        """发射事件到队列"""
        logger.debug("SSE 发射事件", conversation_id=self.conversation_id, event_type=event.type)
        queue = self._queues.get(self.conversation_id)
        if queue:
            await queue.put(event)
        else:
            logger.warning("SSE 队列不存在", conversation_id=self.conversation_id)

    async def emit_batch(self, events: List[Event]) -> None:
        """批量发射"""
        for event in events:
            await self.emit(event)

    def get_queue(self) -> asyncio.Queue:
        """获取事件队列（供 API 层读取）"""
        return self._queues[self.conversation_id]

    @classmethod
    def get_queue_for(cls, conversation_id: str) -> Optional[asyncio.Queue]:
        """获取指定会话的队列"""
        return cls._queues.get(conversation_id)
