import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models import (
    Agent,
    Artifact,
    Conversation,
    Message,
    ModelConfig,
    ModelProvider,
    Task,
    ToolDefinition,
    ToolInvocation,
    User,
    WorkflowRun,
)
from app.services.ark import LLMStreamEvent, ArkClient
from app.services.agents.function_loop import run_agent_function_call_loop
from app.services.agents.tool_loop import build_tools_for_agent, execute_tool_by_name
from app.services.tools.builtins.artifact.export import export_artifact
from app.services.llm_gateway import stream_model_config_chat
from app.services.workflows.engine import WorkflowEngine
from app.services.workflows.runtime import build_edge_states, build_node_states


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

    @pytest.mark.asyncio
    async def test_mock_stream_with_pdf_tool(self) -> None:
        client = ArkClient()
        events: list[LLMStreamEvent] = []
        async for event in client._mock_stream(
            [{"role": "user", "content": "请生成 PDF 项目方案"}],
            purpose="chat",
            tools=[{"type": "function", "function": {"name": "artifact.create_pdf"}}],
        ):
            events.append(event)

        tool_call_event = next(event for event in events if event.type == "tool_calls")
        assert tool_call_event.tool_calls
        assert tool_call_event.tool_calls[0]["function"]["name"] == "artifact.create_pdf"

    @pytest.mark.asyncio
    async def test_stream_chat_sends_tool_choice_auto(self, client: ArkClient) -> None:
        captured: dict[str, Any] = {}

        async def fake_stream_model(model: str, body: dict[str, Any]) -> Any:
            captured.update(body)
            yield LLMStreamEvent(type="done", usage={}, model=model)

        with patch.object(client, "_api_key", return_value="test-key"):
            with patch.object(client, "_stream_model", fake_stream_model):
                events = [
                    event
                    async for event in client.stream_chat(
                        [{"role": "user", "content": "请生成 PDF"}],
                        tools=[{"type": "function", "function": {"name": "artifact.create_pdf"}}],
                    )
                ]

        assert events[-1].type == "done"
        assert captured["tools"][0]["function"]["name"] == "artifact.create_pdf"
        assert captured["tool_choice"] == "auto"

    @pytest.mark.asyncio
    async def test_stream_model_parses_tool_calls_with_separate_finish_chunk(self, client: ArkClient) -> None:
        class FakeStreamResponse:
            status_code = 200

            async def __aenter__(self) -> "FakeStreamResponse":
                return self

            async def __aexit__(self, *_args: Any) -> None:
                return None

            async def aiter_lines(self) -> Any:
                yield (
                    'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_pdf",'
                    '"type":"function","function":{"name":"artifact.create_pdf","arguments":"{}"}}]}}]}'
                )
                yield 'data: {"choices":[{"delta":{},"finish_reason":"tool_calls"}]}'
                yield "data: [DONE]"

            async def aread(self) -> bytes:
                return b""

        class FakeAsyncClient:
            def __init__(self, *_args: Any, **_kwargs: Any) -> None:
                pass

            async def __aenter__(self) -> "FakeAsyncClient":
                return self

            async def __aexit__(self, *_args: Any) -> None:
                return None

            def stream(self, *_args: Any, **_kwargs: Any) -> FakeStreamResponse:
                return FakeStreamResponse()

        with patch.object(client, "_api_key", return_value="test-key"):
            with patch("app.services.ark.httpx.AsyncClient", FakeAsyncClient):
                events = [
                    event
                    async for event in client._stream_model(
                        "test-model",
                        {"model": "test-model", "messages": [], "stream": True},
                    )
                ]

        tool_call_event = next(event for event in events if event.type == "tool_calls")
        assert tool_call_event.tool_calls
        assert tool_call_event.tool_calls[0]["function"]["name"] == "artifact.create_pdf"

    @pytest.mark.asyncio
    async def test_stream_model_requests_once(self, client: ArkClient) -> None:
        """_stream_model should not issue a second HTTP stream after done."""

        class FakeStreamResponse:
            status_code = 200

            async def __aenter__(self) -> "FakeStreamResponse":
                return self

            async def __aexit__(self, *_args: Any) -> None:
                return None

            async def aiter_lines(self) -> Any:
                yield 'data: {"choices":[{"delta":{"content":"hello"}}]}'
                yield 'data: {"usage":{"input_tokens":1,"output_tokens":1},"choices":[]}'
                yield "data: [DONE]"

            async def aread(self) -> bytes:
                return b""

        class FakeAsyncClient:
            stream_calls = 0

            def __init__(self, *_args: Any, **_kwargs: Any) -> None:
                pass

            async def __aenter__(self) -> "FakeAsyncClient":
                return self

            async def __aexit__(self, *_args: Any) -> None:
                return None

            def stream(self, *_args: Any, **_kwargs: Any) -> FakeStreamResponse:
                type(self).stream_calls += 1
                return FakeStreamResponse()

        with patch.object(client, "_api_key", return_value="test-key"):
            with patch("app.services.ark.httpx.AsyncClient", FakeAsyncClient):
                events = [
                    event
                    async for event in client._stream_model(
                        "test-model",
                        {"model": "test-model", "messages": [], "stream": True},
                    )
                ]

        assert FakeAsyncClient.stream_calls == 1
        assert [event.type for event in events] == ["delta", "usage", "done"]


class TestOpenAICompatibleToolCalls:
    @pytest.mark.asyncio
    async def test_stream_model_config_chat_sends_tool_choice_auto(self) -> None:
        db = _memory_session()
        provider = ModelProvider(
            id="provider-tools",
            name="Tool Provider",
            provider_type="openai_compatible",
            base_url="https://example.test/api/v3",
            api_key_ref="test-key",
            default_model="tool-model",
            status="active",
            config={"timeout_seconds": 10},
        )
        model = ModelConfig(
            id="model-tools",
            provider_id=provider.id,
            name="Tool Model",
            model_id="tool-model",
            status="active",
            max_output_tokens=1024,
        )
        db.add_all([provider, model])
        db.commit()
        captured: dict[str, Any] = {}

        class FakeStreamResponse:
            status_code = 200

            async def __aenter__(self) -> "FakeStreamResponse":
                return self

            async def __aexit__(self, *_args: Any) -> None:
                return None

            async def aiter_lines(self) -> Any:
                yield "data: [DONE]"

            async def aread(self) -> bytes:
                return b""

        class FakeAsyncClient:
            def __init__(self, *_args: Any, **_kwargs: Any) -> None:
                pass

            async def __aenter__(self) -> "FakeAsyncClient":
                return self

            async def __aexit__(self, *_args: Any) -> None:
                return None

            def stream(self, *_args: Any, **kwargs: Any) -> FakeStreamResponse:
                captured.update(kwargs.get("json") or {})
                return FakeStreamResponse()

        with patch("app.services.llm_gateway.httpx.AsyncClient", FakeAsyncClient):
            events = [
                event
                async for event in stream_model_config_chat(
                    db,
                    model.id,
                    [{"role": "user", "content": "请生成 PDF"}],
                    tools=[{"type": "function", "function": {"name": "artifact.create_pdf"}}],
                )
            ]

        assert events[-1].type == "done"
        assert captured["tools"][0]["function"]["name"] == "artifact.create_pdf"
        assert captured["tool_choice"] == "auto"


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

        with patch("app.services.agents.tool_loop.invoke_tool") as mock_invoke:
            mock_invoke.return_value = {
                "result": {"status": "succeeded", "path": "/health"},
                "invocation_id": "tool-run-1",
            }
            result = await execute_tool_by_name(
                db,
                agent=agent,
                user=user,
                conversation=conversation,
                tool_name="api.test",
                arguments={"path": "/health"},
            )

        assert result["status"] == "succeeded"
        assert result["invocation_id"] == "tool-run-1"
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

    @pytest.mark.asyncio
    async def test_artifact_tool_call_creates_real_card_and_export(self) -> None:
        db = _memory_session()
        user, conversation, user_message = _user_conversation_message(db, "请生成 PDF 项目方案")
        agent = Agent(
            owner_id=user.id,
            name="Document Agent",
            type="document",
            description="Writes documents",
            config={"tools": ["artifact.create_pdf"]},
            capabilities=[],
        )
        db.add(agent)
        db.commit()

        calls: list[list[dict[str, Any]]] = []

        async def fake_stream_chat(messages: list[dict[str, Any]], **_kwargs: Any) -> Any:
            calls.append(messages)
            if len(calls) == 1:
                yield LLMStreamEvent(
                    type="tool_calls",
                    tool_calls=[
                        {
                            "id": "call-pdf",
                            "type": "function",
                            "function": {
                                "name": "artifact.create_pdf",
                                "arguments": json.dumps(
                                    {"title": "中文项目方案", "body": "目标\n- 第一项\n- 第二项"},
                                    ensure_ascii=False,
                                ),
                            },
                        }
                    ],
                )
                yield LLMStreamEvent(type="done", usage={})
                return
            yield LLMStreamEvent(type="delta", text="PDF 已生成，可以预览和导出。")
            yield LLMStreamEvent(type="done", usage={})

        with patch("app.services.agents.function_loop.ark_client.stream_chat", fake_stream_chat):
            with patch("app.services.agents.function_loop.event_bus.publish", new_callable=AsyncMock):
                result = await run_agent_function_call_loop(
                    db,
                    conversation=conversation,
                    user_message=user_message,
                    agent=agent,
                    prompt="请生成 PDF 项目方案",
                    channel=f"conversation:{conversation.id}",
                    mode="unit-test",
                )

        artifact = db.scalar(select(Artifact).where(Artifact.conversation_id == conversation.id))
        preview = db.scalar(select(Message).where(Message.content_type == "preview_card"))
        tool_output = result.tool_results[0]["result"]["output"]

        assert artifact is not None
        assert preview is not None
        assert tool_output["artifact_id"] == artifact.id
        assert tool_output["format"] == "pdf"
        assert tool_output["preview_url"].endswith(f"/artifacts/{artifact.id}/preview")
        assert tool_output["export_url"].endswith(f"/artifacts/{artifact.id}/export?format=pdf")
        assert tool_output["filename"].endswith(".pdf")
        assert tool_output["media_type"] == "application/pdf"
        assert any(message.get("role") == "tool" for message in calls[1])

    @pytest.mark.parametrize(
        ("tool_name", "prompt", "expected_format", "expected_media_type", "extension"),
        [
            (
                "artifact.create_docx",
                "请生成 Word 项目方案",
                "docx",
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                ".docx",
            ),
            (
                "artifact.create_xlsx",
                "请生成 Excel 项目排期表",
                "xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                ".xlsx",
            ),
            (
                "artifact.create_pptx",
                "请生成 PPT 汇报材料",
                "pptx",
                "application/vnd.openxmlformats-officedocument.presentationml.presentation",
                ".pptx",
            ),
        ],
    )
    @pytest.mark.asyncio
    async def test_office_artifact_tool_calls_create_cards_and_exports(
        self,
        tool_name: str,
        prompt: str,
        expected_format: str,
        expected_media_type: str,
        extension: str,
    ) -> None:
        db = _memory_session()
        user, conversation, user_message = _user_conversation_message(db, prompt)
        agent = Agent(
            owner_id=user.id,
            name="Office Agent",
            type="document",
            description="Writes office artifacts",
            config={"tools": [tool_name]},
            capabilities=[],
        )
        db.add(agent)
        db.commit()

        async def fake_stream_chat(messages: list[dict[str, Any]], **_kwargs: Any) -> Any:
            if not any(message.get("role") == "tool" for message in messages):
                yield LLMStreamEvent(
                    type="tool_calls",
                    tool_calls=[
                        {
                            "id": f"call-{expected_format}",
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "arguments": json.dumps(
                                    {"title": f"中文{expected_format}产物", "body": "目标\n- 第一项\n- 第二项"},
                                    ensure_ascii=False,
                                ),
                            },
                        }
                    ],
                )
                yield LLMStreamEvent(type="done", usage={})
                return
            yield LLMStreamEvent(type="delta", text=f"{expected_format} 已生成。")
            yield LLMStreamEvent(type="done", usage={})

        with patch("app.services.agents.function_loop.ark_client.stream_chat", fake_stream_chat):
            with patch("app.services.agents.function_loop.event_bus.publish", new_callable=AsyncMock):
                result = await run_agent_function_call_loop(
                    db,
                    conversation=conversation,
                    user_message=user_message,
                    agent=agent,
                    prompt=prompt,
                    channel=f"conversation:{conversation.id}",
                    mode="unit-test",
                )

        artifact = db.scalar(select(Artifact).where(Artifact.conversation_id == conversation.id))
        preview = db.scalar(select(Message).where(Message.content_type == "preview_card"))
        tool_output = result.tool_results[0]["result"]["output"]
        exported = export_artifact(artifact, expected_format) if artifact else None

        assert artifact is not None
        assert preview is not None
        assert preview.content["artifact_id"] == artifact.id
        assert preview.content["format"] == expected_format
        assert preview.content["export_url"].endswith(
            f"/artifacts/{artifact.id}/export?format={expected_format}"
        )
        assert preview.content["media_type"] == expected_media_type
        assert tool_output["artifact_id"] == artifact.id
        assert tool_output["format"] == expected_format
        assert tool_output["export_url"].endswith(
            f"/artifacts/{artifact.id}/export?format={expected_format}"
        )
        assert tool_output["filename"].endswith(extension)
        assert tool_output["media_type"] == expected_media_type
        assert exported is not None
        assert exported.media_type == expected_media_type
        assert exported.filename.endswith(extension)
        assert len(exported.content) > 1000

    @pytest.mark.asyncio
    async def test_unauthorized_tool_call_does_not_create_artifact(self) -> None:
        db = _memory_session()
        user, conversation, user_message = _user_conversation_message(db, "请生成 PDF")
        agent = Agent(
            owner_id=user.id,
            name="Chat Agent",
            type="chat",
            description="No tools",
            config={"tools": []},
            capabilities=[],
        )
        db.add(agent)
        db.commit()

        async def fake_stream_chat(messages: list[dict[str, Any]], **_kwargs: Any) -> Any:
            if not any(message.get("role") == "tool" for message in messages):
                yield LLMStreamEvent(
                    type="tool_calls",
                    tool_calls=[
                        {
                            "id": "call-pdf",
                            "type": "function",
                            "function": {"name": "artifact.create_pdf", "arguments": "{}"},
                        }
                    ],
                )
                yield LLMStreamEvent(type="done", usage={})
                return
            yield LLMStreamEvent(type="delta", text="我没有生成 PDF 的工具权限。")
            yield LLMStreamEvent(type="done", usage={})

        with patch("app.services.agents.function_loop.ark_client.stream_chat", fake_stream_chat):
            with patch("app.services.agents.function_loop.event_bus.publish", new_callable=AsyncMock):
                result = await run_agent_function_call_loop(
                    db,
                    conversation=conversation,
                    user_message=user_message,
                    agent=agent,
                    prompt="请生成 PDF",
                    channel=f"conversation:{conversation.id}",
                    mode="unit-test",
                )

        assert db.scalar(select(Artifact)) is None
        assert db.scalar(select(Message).where(Message.content_type == "preview_card")) is None
        assert result.tool_results[0]["status"] == "failed"
        assert "授权" in result.tool_results[0]["result"]["output"]

    @pytest.mark.asyncio
    async def test_custom_python_tool_executes_through_agent_loop(self) -> None:
        db = _memory_session()
        user, conversation, user_message = _user_conversation_message(db, "echo agenthub")
        custom_tool = ToolDefinition(
            owner_id=user.id,
            name="agent.custom_echo_loop",
            display_name="Agent Custom Echo Loop",
            description="Echoes input.",
            type="custom_python",
            status="active",
            input_schema={
                "type": "object",
                "properties": {"input": {"type": "string"}},
                "required": ["input"],
            },
            implementation={
                "language": "python",
                "code": "result = {'echo': arguments.get('input'), 'ok': True}",
            },
        )
        agent = Agent(
            owner_id=user.id,
            name="Custom Agent",
            type="custom",
            config={"tools": [custom_tool.name]},
            capabilities=[],
        )
        db.add_all([custom_tool, agent])
        db.commit()

        async def fake_stream_chat(messages: list[dict[str, Any]], **_kwargs: Any) -> Any:
            if not any(message.get("role") == "tool" for message in messages):
                yield LLMStreamEvent(
                    type="tool_calls",
                    tool_calls=[
                        {
                            "id": "call-custom",
                            "type": "function",
                            "function": {
                                "name": custom_tool.name,
                                "arguments": json.dumps({"input": "agenthub"}),
                            },
                        }
                    ],
                )
                yield LLMStreamEvent(type="done", usage={})
                return
            yield LLMStreamEvent(type="delta", text="custom tool done")
            yield LLMStreamEvent(type="done", usage={})

        with patch("app.services.agents.function_loop.ark_client.stream_chat", fake_stream_chat):
            with patch("app.services.agents.function_loop.event_bus.publish", new_callable=AsyncMock):
                result = await run_agent_function_call_loop(
                    db,
                    conversation=conversation,
                    user_message=user_message,
                    agent=agent,
                    prompt="echo agenthub",
                    channel=f"conversation:{conversation.id}",
                    mode="unit-test",
                )

        invocation = db.scalar(select(ToolInvocation).where(ToolInvocation.tool_name == custom_tool.name))
        output = result.tool_results[0]["result"]["output"]

        assert invocation is not None
        assert invocation.status == "succeeded"
        assert output["result"]["echo"] == "agenthub"
        assert result.text.endswith("custom tool done")

    @pytest.mark.asyncio
    async def test_workflow_agent_node_can_call_artifact_tool(self) -> None:
        db = _memory_session()
        user, conversation, user_message = _user_conversation_message(db, "生成 HTML")
        agent = Agent(
            id="workflow-writer-agent",
            owner_id=user.id,
            name="Workflow Writer",
            type="writer",
            config={"tools": ["artifact.create_html"]},
            capabilities=[],
        )
        task = Task(
            conversation_id=conversation.id,
            creator_id=user.id,
            title="workflow",
            description="workflow",
            status="EXECUTING",
        )
        workflow = {
            "mode": "canvas",
            "output_mode": "independent_messages",
            "nodes": [
                {"id": "start", "type": "start", "title": "Start"},
                {"id": "writer", "type": "agent", "title": "Writer", "agent_id": agent.id},
                {"id": "end", "type": "end", "title": "End"},
            ],
            "edges": [["start", "writer"], ["writer", "end"]],
        }
        run = WorkflowRun(
            conversation_id=conversation.id,
            trigger_message_id=user_message.id,
            started_by=user.id,
            status="running",
            mode="canvas",
            workflow_snapshot=workflow,
            node_states=build_node_states(workflow),
            edge_states=build_edge_states(workflow),
            events=[],
            progress=0,
        )
        db.add_all([agent, task, run])
        db.commit()

        async def fake_stream_chat(messages: list[dict[str, Any]], **_kwargs: Any) -> Any:
            if not any(message.get("role") == "tool" for message in messages):
                yield LLMStreamEvent(
                    type="tool_calls",
                    tool_calls=[
                        {
                            "id": "call-html",
                            "type": "function",
                            "function": {
                                "name": "artifact.create_html",
                                "arguments": json.dumps(
                                    {"title": "Workflow HTML", "html": "<h1>AgentHub</h1>"},
                                ),
                            },
                        }
                    ],
                )
                yield LLMStreamEvent(type="done", usage={})
                return
            yield LLMStreamEvent(type="delta", text="HTML 已生成。")
            yield LLMStreamEvent(type="done", usage={})

        with patch("app.services.agents.function_loop.ark_client.stream_chat", fake_stream_chat):
            with patch("app.services.agents.function_loop.event_bus.publish", new_callable=AsyncMock):
                with patch("app.services.workflows.events.event_bus.publish", new_callable=AsyncMock):
                    result = await WorkflowEngine(
                        db,
                        conversation=conversation,
                        user_message=user_message,
                        task=task,
                        workflow_run=run,
                        workflow=workflow,
                        prompt="生成 HTML",
                        channel=f"conversation:{conversation.id}",
                        agents=[agent],
                    ).run()

        artifact = db.scalar(select(Artifact).where(Artifact.conversation_id == conversation.id))
        writer_output = result.outputs["writer"]

        assert artifact is not None
        assert writer_output["tool_results"][0]["tool_name"] == "artifact.create_html"
        assert writer_output["tool_results"][0]["result"]["output"]["artifact_id"] == artifact.id
        assert run.status == "completed"


def _memory_session() -> Any:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return session_factory()


def _user_conversation_message(db, text: str) -> tuple[User, Conversation, Message]:
    user = User(
        id="function-user-1",
        email=f"{id(db)}@function.example",
        username=f"function-{id(db)}",
        password_hash="x",
        display_name="Function User",
    )
    conversation = Conversation(creator_id=user.id, chat_type="single", title="Function Loop")
    db.add_all([user, conversation])
    db.flush()
    message = Message(
        conversation_id=conversation.id,
        sender_type="user",
        sender_id=user.id,
        sender_name=user.display_name,
        content_type="text",
        content={"text": text},
        status="sent",
        extra={},
    )
    db.add(message)
    db.commit()
    db.refresh(conversation)
    db.refresh(message)
    return user, conversation, message


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
