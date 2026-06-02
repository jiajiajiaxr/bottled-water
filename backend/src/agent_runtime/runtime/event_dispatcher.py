"""
事件分发器

负责将事件并发投递到多个 Sink：
- SSE → 前端实时流
- Logger → 日志系统
- Persistence → 持久化存储
- 支持自定义 Sink 扩展

职责上提：由 Session 层统一管理，Orchestrator 只负责产生事件。

事件分类（按 type 前缀）：
- control.*  → 控制事件（调度决策、看门狗等，系统内部消费）
- agent.*    → Agent 观测事件（thinking、token、tool_call 等，前端可展示）
- user.*     → 用户相关事件（用户输入、等待输入等）
- system.*   → 系统级事件（session 生命周期、round 生命周期等）
"""

import fnmatch
from typing import List, Callable, Union

from common.logger import get_logger
from ..core.types import Event
from ..core.interfaces import EventSink

logger = get_logger(__name__)


EventFilter = Union[str, Callable[[Event], bool], None]


class _SinkEntry:
    """带过滤条件的 Sink 注册项"""

    def __init__(self, sink: EventSink, event_filter: EventFilter = None):
        self.sink = sink
        self.event_filter = event_filter

    def matches(self, event: Event) -> bool:
        """判断事件是否匹配本 Sink 的过滤条件"""
        if self.event_filter is None:
            return True
        if callable(self.event_filter):
            return self.event_filter(event)
        if isinstance(self.event_filter, str):
            return fnmatch.fnmatch(event.type, self.event_filter)
        return True


class EventDispatcher:
    """事件分发器 - 多 Sink 并发消费，支持按事件类型过滤"""

    def __init__(self):
        self._entries: List[_SinkEntry] = []

    def register_sink(self, sink: EventSink, event_filter: EventFilter = None) -> "EventDispatcher":
        """注册事件 Sink（链式调用）

        Args:
            sink: 事件接收器
            event_filter: 事件过滤条件
                - None: 接收所有事件
                - str: 通配符模式，如 "agent.*"、"system.*"
                - Callable[[Event], bool]: 自定义过滤函数
        """
        self._entries.append(_SinkEntry(sink, event_filter))
        return self

    def unregister_sink(self, sink: EventSink) -> None:
        """注销事件 Sink"""
        self._entries = [e for e in self._entries if e.sink is not sink]

    async def dispatch(self, event: Event) -> None:
        """将事件分发给所有匹配的 Sink"""
        if not self._entries:
            return

        for entry in self._entries:
            if not entry.matches(event):
                continue
            try:
                await entry.sink.emit(event)
            except Exception as e:
                logger.warning(
                    "事件 Sink 投递失败", sink_type=type(entry.sink).__name__, error=str(e)
                )

    async def dispatch_batch(self, events: List[Event]) -> None:
        """批量分发事件"""
        for event in events:
            await self.dispatch(event)
