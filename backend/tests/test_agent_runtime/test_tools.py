"""
测试工具注册表和执行器
"""

import pytest

from agent_runtime.tools.registry import ToolRegistry
from agent_runtime.tools.executor import ToolExecutorImpl
from agent_runtime.core.types import ToolCall, ToolResult


class TestToolRegistry:
    """测试 ToolRegistry"""

    @pytest.fixture
    def registry(self):
        return ToolRegistry()

    def test_register(self, registry):
        def handler(path: str) -> str:
            return f"content of {path}"

        registry.register(
            name="file_read",
            description="读取文件内容",
            parameters={"type": "object", "properties": {"path": {"type": "string"}}},
            handler=handler,
        )

        tool = registry.get_tool("file_read")
        assert tool is not None
        assert tool["name"] == "file_read"
        assert tool["description"] == "读取文件内容"

        handler_fn = registry.get_handler("file_read")
        assert handler_fn is not None
        assert handler_fn("/tmp/test.txt") == "content of /tmp/test.txt"

    def test_list_tools(self, registry):
        registry.register("tool1", "工具1", {}, lambda: None)
        registry.register("tool2", "工具2", {}, lambda: None)

        tools = registry.list_tools()
        assert len(tools) == 2
        assert all(t["type"] == "function" for t in tools)
        assert tools[0]["function"]["name"] == "tool1"
        assert tools[1]["function"]["name"] == "tool2"

    def test_get_tool_not_found(self, registry):
        assert registry.get_tool("nonexistent") is None
        assert registry.get_handler("nonexistent") is None

    def test_unregister(self, registry):
        registry.register("tool1", "工具1", {}, lambda: None)
        assert registry.get_tool("tool1") is not None

        registry.unregister("tool1")
        assert registry.get_tool("tool1") is None
        assert registry.get_handler("tool1") is None


class TestToolExecutorImpl:
    """测试 ToolExecutorImpl"""

    @pytest.fixture
    def registry(self):
        reg = ToolRegistry()
        reg.register(
            "add",
            "加法",
            {"type": "object", "properties": {"a": {"type": "number"}, "b": {"type": "number"}}},
            lambda a, b: a + b,
        )
        reg.register(
            "async_add",
            "异步加法",
            {"type": "object", "properties": {"a": {"type": "number"}, "b": {"type": "number"}}},
            lambda a, b: a + b,  # 同步版本用于测试
        )
        return reg

    @pytest.fixture
    def executor(self, registry):
        return ToolExecutorImpl(registry)

    @pytest.mark.asyncio
    async def test_execute_sync_tool(self, executor):
        call = ToolCall(tool_name="add", parameters={"a": 1, "b": 2}, call_id="call_1")
        result = await executor.execute(call)
        assert isinstance(result, ToolResult)
        assert result.success is True
        assert result.result == 3
        assert result.call_id == "call_1"
        assert result.error is None

    @pytest.mark.asyncio
    async def test_execute_not_found(self, executor):
        call = ToolCall(tool_name="nonexistent", parameters={}, call_id="call_1")
        result = await executor.execute(call)
        assert result.success is False
        assert result.error == "Tool not found: nonexistent"

    @pytest.mark.asyncio
    async def test_execute_error(self, executor):
        # 注册一个会抛出异常的工具
        def bad_tool():
            raise ValueError("出错了")

        executor.registry.register("bad", "坏工具", {}, bad_tool)
        call = ToolCall(tool_name="bad", parameters={}, call_id="call_1")
        result = await executor.execute(call)
        assert result.success is False
        assert "出错了" in result.error

    def test_list_tools(self, executor):
        tools = executor.list_tools()
        assert len(tools) == 3  # add, async_add, bad
