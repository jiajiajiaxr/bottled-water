"""
agent_runtime 测试 fixtures
"""

import pytest
from typing import List, Dict, Any
from agent_runtime import (
    AgentConfig,
    Event,
    Message,
)
from agent_runtime import PersistenceBackend, EventSink, ToolExecutor

# 从项目根目录加载 .env
from dotenv import load_dotenv
from model_provider import create_provider, ModelConfig, ChatResponse, StreamChunk
from model_provider.core.interfaces import BaseModelProvider

# 加载环境变量（从项目根目录）
import os

env_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env")
load_dotenv(env_path)

# ---------------------------------------------------------------------------
# Mock Model Provider
# ---------------------------------------------------------------------------


class MockModelProvider(BaseModelProvider):
    """用于测试的模型提供者 mock"""

    def __init__(self):
        # 绕过 BaseModelProvider 的 config 要求
        self.config = {}
        self.model = "mock"
        self.responses: List[ChatResponse] = []
        self.call_count = 0

    async def chat(
        self,
        messages=None,
        system_prompt=None,
        tools=None,
        temperature=0.7,
        max_tokens=None,
    ) -> ChatResponse:
        self.call_count += 1
        if self.responses:
            idx = min(self.call_count - 1, len(self.responses) - 1)
            return self.responses[idx]
        return ChatResponse(content="mock response")

    async def chat_stream(self, messages=None, system_prompt=None, tools=None, temperature=0.7, max_tokens=None):
        yield StreamChunk(content="mock", finish_reason="stop")


@pytest.fixture
def mock_provider():
    return MockModelProvider()


@pytest.fixture
def api_key():
    key = os.environ.get("ARK_API_KEY")
    if not key:
        pytest.skip("ARK_API_KEY not found in environment")
    return key


@pytest.fixture
def endpoint_id():
    eid = os.environ.get("ARK_ENDPOINT_ID")
    if not eid:
        pytest.skip("ARK_ENDPOINT_ID not found in environment")
    return eid


@pytest.fixture
def provider(api_key, endpoint_id):
    """创建 ArkProvider 实例"""
    return create_provider(
        ModelConfig(
            provider="ark",
            model=endpoint_id,
            api_key=api_key,
        )
    )


# ---------------------------------------------------------------------------
# Mock Persistence Backend
# ---------------------------------------------------------------------------


class MockPersistenceBackend(PersistenceBackend):
    """用于测试的持久化后端 mock"""

    def __init__(self):
        self.messages: List[Message] = []
        self.blackboards: Dict[str, dict] = {}
        self.agent_contexts: Dict[str, List[dict]] = {}

    async def create_conversation(self, metadata: dict) -> str:
        return metadata.get("id", "mock_conv_id")

    async def load_messages(self, conversation_id: str, limit: int = 100) -> List[Message]:
        return self.messages[-limit:]

    async def save_message(self, message: Message) -> None:
        self.messages.append(message)

    async def load_blackboard(self, conversation_id: str) -> dict:
        return self.blackboards.get(conversation_id, {})

    async def save_blackboard(self, conversation_id: str, data: dict) -> None:
        self.blackboards[conversation_id] = data

    async def load_agent_context(self, agent_id: str, conversation_id: str) -> List[dict]:
        key = f"{agent_id}:{conversation_id}"
        return self.agent_contexts.get(key, [])

    async def save_agent_context(
        self, agent_id: str, conversation_id: str, frames: List[dict]
    ) -> None:
        key = f"{agent_id}:{conversation_id}"
        self.agent_contexts[key] = frames


# ---------------------------------------------------------------------------
# Mock Event Sink
# ---------------------------------------------------------------------------


class MockEventSink(EventSink):
    """用于测试的事件接收器 mock"""

    def __init__(self):
        self.events: List[Event] = []

    async def emit(self, event: Event) -> None:
        self.events.append(event)

    async def emit_batch(self, events: List[Event]) -> None:
        self.events.extend(events)


# ---------------------------------------------------------------------------
# Mock Tool Executor
# ---------------------------------------------------------------------------


class MockToolExecutor(ToolExecutor):
    """用于测试的工具执行器 mock"""

    def __init__(self, tools: List[Dict] = None):
        self._tools = tools or []
        self.calls: List[dict] = []

    async def execute(self, tool_call) -> Any:
        from agent_runtime import ToolResult

        self.calls.append({"tool_name": tool_call.tool_name, "parameters": tool_call.parameters})
        return ToolResult(
            call_id=tool_call.call_id,
            success=True,
            result={"tool": tool_call.tool_name, "params": tool_call.parameters, "result": "mock_result"},
        )

    def list_tools(self) -> List[Dict]:
        return self._tools


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_persistence():
    return MockPersistenceBackend()


@pytest.fixture
def mock_event_sink():
    return MockEventSink()


@pytest.fixture
def mock_tool_executor():
    return MockToolExecutor()


@pytest.fixture
def sample_agent_config():
    return AgentConfig(
        id="coder",
        name="程序员",
        system_prompt="你是一个资深程序员。",
        role="worker",
        tools=["file_read", "file_write"],
    )


@pytest.fixture
def sample_agents():
    return {
        "coder": AgentConfig(
            id="coder",
            name="程序员",
            system_prompt="你是一个资深程序员。",
            role="worker",
        ),
        "reviewer": AgentConfig(
            id="reviewer",
            name="代码审查员",
            system_prompt="你是一个严格的代码审查员。",
            role="verifier",
        ),
    }
