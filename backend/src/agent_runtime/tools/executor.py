"""
工具执行器

负责执行工具调用，处理异常，返回结果。
"""

from typing import Any, Dict

from common.logger import get_logger
from .registry import ToolRegistry
from ..core.types import ToolCall, ToolResult

logger = get_logger(__name__)


class ToolExecutorImpl:
    """工具执行器实现"""

    def __init__(self, registry: ToolRegistry):
        self.registry = registry

    async def execute(self, tool_call: ToolCall) -> ToolResult:
        """执行工具调用"""
        logger.info("工具执行", tool=tool_call.tool_name, call_id=tool_call.call_id)
        handler = self.registry.get_handler(tool_call.tool_name)
        if not handler:
            logger.warning("工具未找到", tool=tool_call.tool_name)
            return ToolResult(
                call_id=tool_call.call_id,
                success=False,
                result=None,
                error=f"Tool not found: {tool_call.tool_name}",
            )

        try:
            # 支持同步和异步 handler
            import asyncio
            if asyncio.iscoroutinefunction(handler):
                result = await handler(**tool_call.parameters)
            else:
                result = handler(**tool_call.parameters)

            logger.info("工具执行成功", tool=tool_call.tool_name, call_id=tool_call.call_id)
            return ToolResult(
                call_id=tool_call.call_id,
                success=True,
                result=result,
            )
        except Exception as e:
            logger.error("工具执行失败", tool=tool_call.tool_name, call_id=tool_call.call_id, error=str(e))
            return ToolResult(
                call_id=tool_call.call_id,
                success=False,
                result=None,
                error=str(e),
            )

    def list_tools(self) -> list:
        """列出可用工具"""
        return self.registry.list_tools()
