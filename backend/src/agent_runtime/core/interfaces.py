"""
运行时依赖的外部接口

由 app 层或测试提供具体实现。
"""

from abc import ABC, abstractmethod
from typing import List, Dict

from .types import Event, Message, ToolCall, ToolResult


class PersistenceBackend(ABC):
    """持久化后端接口"""

    @abstractmethod
    async def create_conversation(self, metadata: dict) -> str:
        """创建会话，返回 conversation_id"""
        pass

    @abstractmethod
    async def load_messages(self, conversation_id: str, limit: int = 100) -> List[Message]:
        """加载消息历史"""
        pass

    @abstractmethod
    async def save_message(self, message: Message) -> None:
        """保存单条消息"""
        pass

    @abstractmethod
    async def load_blackboard(self, conversation_id: str) -> dict:
        """加载 Blackboard 数据"""
        pass

    @abstractmethod
    async def save_blackboard(self, conversation_id: str, data: dict) -> None:
        """保存 Blackboard 数据"""
        pass

    @abstractmethod
    async def load_agent_context(self, agent_id: str, conversation_id: str) -> List[dict]:
        """加载 Agent 上下文"""
        pass

    @abstractmethod
    async def save_agent_context(
        self, agent_id: str, conversation_id: str, frames: List[dict]
    ) -> None:
        """保存 Agent 上下文"""
        pass


class EventSink(ABC):
    """事件投递接口"""

    @abstractmethod
    async def emit(self, event: Event) -> None:
        """发射单个事件"""
        pass

    @abstractmethod
    async def emit_batch(self, events: List[Event]) -> None:
        """批量发射事件"""
        pass


class ToolExecutor(ABC):
    """工具执行器接口"""

    @abstractmethod
    async def execute(self, tool_call: ToolCall) -> ToolResult:
        """执行工具调用"""
        pass

    @abstractmethod
    def list_tools(self) -> List[Dict]:
        """列出可用工具"""
        pass
