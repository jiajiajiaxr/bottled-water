"""
agent_runtime 适配器层

将新 agent_runtime 运行时桥接到现有 app 层：
- ToolExecutorAdapter: 复用旧的 build_tools_for_agent / execute_tool_by_name

这是 app 层唯一直接依赖 agent_runtime 的模块。
"""

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from common.logger import get_logger
from agent_runtime.core.interfaces import ToolExecutor
from agent_runtime.core.types import Event

from app.models import Agent, Conversation

logger = get_logger(__name__)


class ToolExecutorAdapter(ToolExecutor):
    """工具执行器适配器

    将 agent_runtime 的 ToolExecutor 接口桥接到旧的
    build_tools_for_agent / execute_tool_by_name 系统。
    """

    def __init__(
        self,
        db: Session,
        agent: Agent,
        user: Any,
        conversation: Conversation,
    ):
        self.db = db
        self.agent = agent
        self.user = user
        self.conversation = conversation
        self._tools_cache: Optional[List[Dict]] = None

    def list_tools(self) -> List[Dict]:
        """列出可用工具（OpenAI Function Calling 格式）"""
        if self._tools_cache is None:
            from app.services.agentic_runtime import build_tools_for_agent

            self._tools_cache = build_tools_for_agent(self.db, self.agent)
        return self._tools_cache

    async def execute(self, tool_name: str, parameters: Dict[str, Any]) -> Any:
        """执行工具调用"""
        from app.services.agentic_runtime import execute_tool_by_name

        logger.info("适配器执行工具", tool=tool_name, agent=self.agent.name)
        result = await execute_tool_by_name(
            self.db,
            agent=self.agent,
            user=self.user,
            conversation=self.conversation,
            tool_name=tool_name,
            arguments=parameters,
        )
        return result