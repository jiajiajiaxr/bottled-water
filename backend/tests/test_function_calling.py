from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.ark import LLMStreamEvent, ArkClient
from app.services.agentic_runtime import build_tools_for_agent, execute_tool_by_name
from app.services.agents.function_loop import run_agent_function_call_loop


class TestArkClientToolCalls:
    """测试 ArkClient 对 tool_calls 增量输出的解析。"""

    @pytest.fixture
    def client(self) -> ArkClient:
        return ArkClient()

    @pytest.mark.asyncio
    async def test_stream_model_parses_tool_calls(self, client: ArkClient) -> None:
        """模拟 SSE 流中包含增量 tool_calls，验证正确累积。"""
        # 直接用 patch 替换整个 _stream_model 方法，验证它能产出 tool_calls 事件
        async def fake_stream_model(
            model: str, body: dict[str, Any]
        ) -> Any:
            """模拟包含 tool_calls 的流。"""
            yield LLMStreamEvent(type="delta", text="我来处理文件。", model=model)
            yield LLMStreamEvent(
                type="tool_calls",
                tool_calls=[
                    {
                        "id": "call_abc123",
                        "type": "function",
                        "function": {
                            "name": "file.extract_text",
                            "arguments": '{"file_id": "file-123"}',
                        },
                    }
                ],
                model=model,
            )
            yield LLMStreamEvent(type="done", usage={}, model=model)

        with patch.object(client, "_api_key", return_value="test-key"):
            with patch.object(client, "_stream_model", fake_stream_model):
                events: list[LLMStreamEvent] = []
                async for event in client.stream_chat(
                    [{"role": "user", "content": "提取文件"}],
                    tools=[{"type": "function", "function": {"name": "file.extract_text"}}],
                ):
                    events.append(event)

        # 验证事件序列
        assert any(e.type == "tool_calls" for e in events), "应有 tool_calls 事件"
        tool_call_event = next(e for e in events if e.type == "tool_calls")
        assert tool_call_event.tool_calls is not None
        assert len(tool_call_event.tool_calls) == 1
        tc = tool_call_event.tool_calls[0]
        assert tc["id"] == "call_abc123"
        assert tc["type"] == "function"
        assert tc["function"]["name"] == "file.extract_text"
        assert tc["function"]["arguments"] == '{"file_id": "file-123"}'
        assert any(e.type == "done" for e in events), "应有 done 事件"

    @pytest.mark.asyncio
    async def test_mock_stream_with_tools(self) -> None:
        """测试 _mock_stream 在传入 tools 且用户请求涉及文件时模拟工具调用。"""
        client = ArkClient()
        events: list[LLMStreamEvent] = []
        async for event in client._mock_stream(
            [{"role": "user", "content": "extract text from file"}],
            purpose="chat",
            tools=[{"type": "function", "function": {"name": "file.extract_text"}}],
        ):
            events.append(event)

        assert any(e.type == "tool_calls" for e in events)
        tc_event = next(e for e in events if e.type == "tool_calls")
        assert tc_event.tool_calls
        assert tc_event.tool_calls[0]["function"]["name"] == "file.extract_text"


class TestBuildToolsForAgent:
    """测试 build_tools_for_agent 将 Agent 配置转为 Function Calling 格式。"""

    def test_build_tools_with_builtin_tools(self) -> None:
        """测试内置工具转换。"""
        db = MagicMock()
        agent = MagicMock()
        agent.config = {
            "tools": ["file.extract_text", "sandbox.run"],
        }
        agent.id = "agent-1"
        db.scalars.return_value.all.return_value = []

        tools = build_tools_for_agent(db, agent)

        names = [t["function"]["name"] for t in tools]
        assert "file.extract_text" in names
        assert "sandbox.run" in names
        assert all(t["type"] == "function" for t in tools)

    def test_build_tools_with_skills(self) -> None:
        """测试 Skill 转换为 function 格式。"""
        db = MagicMock()
        agent = MagicMock()
        agent.config = {"skill_ids": ["skill-1"], "tools": []}
        agent.id = "agent-1"

        skill = MagicMock()
        skill.id = "skill-1"
        skill.name = "Test Skill"
        skill.description = "A test skill"
        skill.prompt = "You are a test skill"
        skill.deleted_at = None
        skill.status = "active"

        db.scalars.return_value.all.return_value = [skill]

        tools = build_tools_for_agent(db, agent)

        names = [t["function"]["name"] for t in tools]
        assert "skill.skill-1" in names
        skill_tool = next(t for t in tools if t["function"]["name"] == "skill.skill-1")
        assert skill_tool["function"]["description"] == "A test skill"

    def test_build_tools_empty_config(self) -> None:
        """测试空配置返回空列表。"""
        db = MagicMock()
        agent = MagicMock()
        agent.config = {}
        agent.id = "agent-1"
        db.scalars.return_value.all.return_value = []

        tools = build_tools_for_agent(db, agent)
        assert tools == []


class TestExecuteToolByName:
    """测试 execute_tool_by_name 路由逻辑。"""

    @pytest.mark.asyncio
    async def test_execute_builtin_tool(self) -> None:
        """测试路由到内置工具。"""
        db = MagicMock()
        agent = MagicMock()
        agent.config = {"tools": ["api.test"]}
        agent.id = "agent-1"

        user = MagicMock()
        conversation = MagicMock()
        conversation.id = "conv-1"

        from app.services import tool_registry

        with patch.object(
            tool_registry, "invoke_builtin_tool"
        ) as mock_invoke:
            mock_invoke.return_value = {"status": "succeeded", "path": "/health"}
            result = await execute_tool_by_name(
                db,
                agent=agent,
                user=user,
                conversation=conversation,
                tool_name="api.test",
                arguments={"path": "/health"},
            )

        assert result["status"] == "succeeded"
        mock_invoke.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self) -> None:
        """测试未知工具返回错误。"""
        db = MagicMock()
        agent = MagicMock()
        agent.config = {}
        agent.id = "agent-1"

        result = await execute_tool_by_name(
            db,
            agent=agent,
            user=None,
            conversation=MagicMock(),
            tool_name="unknown.tool",
            arguments={},
        )

        assert result["type"] == "unknown"
        assert result["status"] == "failed"
        assert "未知工具" in result["output"]


class TestAgentFunctionCallLoop:
    """???????????? Function Call Loop?"""

    @pytest.mark.asyncio
    async def test_tool_result_is_fed_back_to_model(self) -> None:
        db = MagicMock()
        db.get.return_value = MagicMock()

        def refresh(obj: Any) -> None:
            if getattr(obj, "id", None) is None:
                obj.id = "assistant-message-1"

        db.refresh.side_effect = refresh
        db.scalars.return_value.all.return_value = []

        conversation = MagicMock()
        conversation.id = "conversation-1"
        conversation.creator_id = "user-1"
        user_message = MagicMock()
        user_message.extra = {}
        agent = MagicMock()
        agent.id = "agent-1"
        agent.name = "Backend Worker"
        agent.type = "backend"
        agent.description = "Backend worker"
        agent.config = {"tools": ["api.test"]}

        calls: list[list[dict[str, Any]]] = []

        async def fake_stream_chat(messages: list[dict[str, Any]], **kwargs: Any) -> Any:
            calls.append(messages)
            if len(calls) == 1:
                yield LLMStreamEvent(type="delta", text="I will test the API.")
                yield LLMStreamEvent(
                    type="tool_calls",
                    tool_calls=[
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {"name": "api.test", "arguments": '{"path": "/health"}'},
                        }
                    ],
                )
                yield LLMStreamEvent(type="done", usage={})
                return
            yield LLMStreamEvent(type="delta", text="API test passed.")
            yield LLMStreamEvent(type="done", usage={})

        with patch("app.services.agents.function_loop.ark_client.stream_chat", fake_stream_chat):
            with patch("app.services.agents.function_loop.execute_tool_by_name", new_callable=AsyncMock) as execute:
                execute.return_value = {"status": "succeeded", "output": {"path": "/health"}}
                with patch("app.services.agents.function_loop.event_bus.publish", new_callable=AsyncMock):
                    result = await run_agent_function_call_loop(
                        db,
                        conversation=conversation,
                        user_message=user_message,
                        agent=agent,
                        prompt="test api",
                        channel="conversation:conversation-1",
                        mode="unit-test",
                    )

        assert result.text == "I will test the API.API test passed."
        execute.assert_awaited_once()
        assert len(calls) == 2
        assert any(message.get("role") == "tool" for message in calls[1])


class TestStreamEventDataclass:
    """测试 LLMStreamEvent dataclass 扩展。"""

    def test_event_with_tool_calls(self) -> None:
        """验证 tool_calls 字段正确存储。"""
        event = LLMStreamEvent(
            type="tool_calls",
            tool_calls=[
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {"name": "test", "arguments": "{}"},
                }
            ],
            model="test-model",
        )
        assert event.type == "tool_calls"
        assert event.tool_calls is not None
        assert len(event.tool_calls) == 1
        assert event.tool_calls[0]["function"]["name"] == "test"

    def test_event_without_tool_calls(self) -> None:
        """验证不含 tool_calls 时字段为 None。"""
        event = LLMStreamEvent(type="delta", text="hello", model="test")
        assert event.tool_calls is None
        assert event.text == "hello"
