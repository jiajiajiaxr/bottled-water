"""
会话入口

用户使用 agent_runtime 的入口。
EventDispatcher 职责上提：由 Session 统一管理，Orchestrator 只负责产生事件。
"""

from typing import List, Optional, AsyncIterator, Dict, Any
import uuid

from model_provider.core.interfaces import BaseModelProvider

from common.logger import get_logger
from ..core.types import AgentConfig, Event
from ..core.interfaces import PersistenceBackend, EventSink, ToolExecutor
from .orchestrator import Orchestrator
from .event_dispatcher import EventDispatcher
from ..strategies.base import Scheduler

logger = get_logger(__name__)


class Session:
    """
    多智能体会话

    纯运行时对象，不依赖 HTTP、数据库、或任何框架。
    所有外部依赖通过接口注入。
    """

    def __init__(
        self,
        session_id: str,
        agents: List[AgentConfig],
        scheduler: Scheduler,
        model_provider: BaseModelProvider,
        persistence: Optional[PersistenceBackend] = None,
        event_sink: Optional[EventSink] = None,
        tool_executor: Optional[ToolExecutor] = None,
    ):
        self.session_id = session_id
        self.agents = {a.id: a for a in agents}
        self.scheduler = scheduler
        self.model_provider = model_provider
        self.persistence = persistence
        self.tool_executor = tool_executor or _NullToolExecutor()

        # 事件分发器（职责上提：Session 层统一管理）
        self.event_dispatcher = EventDispatcher()
        if event_sink:
            self.event_dispatcher.register_sink(event_sink)

        self.orchestrator = Orchestrator(
            session_id=session_id,
            agents=self.agents,
            scheduler=scheduler,
            model_provider=model_provider,
            persistence=persistence,
            tool_executor=self.tool_executor,
        )

    @classmethod
    def create(
        cls,
        agents: List[AgentConfig],
        scheduler: Scheduler,
        model_provider: BaseModelProvider,
        persistence: Optional[PersistenceBackend] = None,
        event_sink: Optional[EventSink] = None,
        tool_executor: Optional[ToolExecutor] = None,
        session_id: Optional[str] = None,
    ) -> "Session":
        """工厂方法，自动分配 session_id（可外部传入）"""
        session_id = session_id or str(uuid.uuid4())
        logger.info(
            "Session 创建",
            session_id=session_id,
            agent_count=len(agents),
            agent_ids=[a.id for a in agents],
            scheduler_type=type(scheduler).__name__,
        )
        return cls(
            session_id=session_id,
            agents=agents,
            scheduler=scheduler,
            model_provider=model_provider,
            persistence=persistence,
            event_sink=event_sink,
            tool_executor=tool_executor,
        )

    async def run(self, user_message: str) -> AsyncIterator[Event]:
        """
        运行会话

        返回事件流，同时通过 EventDispatcher 分发给各 Sink。
        """
        logger.info("Session 运行开始", session_id=self.session_id, message_len=len(user_message))
        try:
            async for event in self.orchestrator.run(user_message):
                # 分发到所有注册的 Sink（不阻塞 yield）
                await self.event_dispatcher.dispatch(event)
                yield event
        except Exception as e:
            logger.error("Session 运行失败", session_id=self.session_id, error=str(e))
            raise
        logger.info("Session 运行结束", session_id=self.session_id)

    async def send_message(self, content: str) -> AsyncIterator[Event]:
        """向运行中的会话发送新消息"""
        async for event in self.orchestrator.handle_user_input(content):
            await self.event_dispatcher.dispatch(event)
            yield event

    def get_status(self) -> dict:
        """获取会话当前状态"""
        return self.orchestrator.get_status()


# 空实现，用于可选依赖的默认值


class _NullEventSink(EventSink):
    async def emit(self, event: Event) -> None:
        pass

    async def emit_batch(self, events: List[Event]) -> None:
        pass


class _NullToolExecutor(ToolExecutor):
    async def execute(self, tool_call) -> Any:
        from agent_runtime import ToolResult

        return ToolResult(
            call_id=tool_call.call_id,
            success=False,
            result=None,
            error="No tool executor configured",
        )

    def list_tools(self) -> List[Dict]:
        return []
