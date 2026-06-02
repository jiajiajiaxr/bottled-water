"""
测试 Agent 自持实体

覆盖：
- 状态机
- inbox/outbox 通信
- 任务执行
- 状态报告
"""

import pytest

from model_provider import ChatResponse
from agent_runtime.runtime.agent import Agent
from agent_runtime.core.types import AgentConfig, AgentState


class TestAgentLifecycle:
    """测试 Agent 生命周期"""

    @pytest.fixture
    def agent(self, mock_provider):
        config = AgentConfig(
            id="coder",
            name="程序员",
            system_prompt="你是一个程序员。",
        )
        return Agent(config=config, model_provider=mock_provider)

    def test_init(self, agent):
        assert agent.id == "coder"
        assert agent.state == AgentState.IDLE
        assert agent.current_task is None
        assert agent.inbox.empty()
        assert agent.outbox.empty()

    @pytest.mark.asyncio
    async def test_assign_task(self, agent):
        await agent.assign("写代码", {})
        assert not agent.inbox.empty()
        msg = agent.inbox.get_nowait()
        assert msg["command"] == "assign"
        assert msg["task"] == "写代码"

    @pytest.mark.asyncio
    async def test_pause(self, agent):
        await agent.pause()
        assert not agent.inbox.empty()
        msg = agent.inbox.get_nowait()
        assert msg["command"] == "pause"

    @pytest.mark.asyncio
    async def test_report_status_idle(self, agent):
        report = await agent.report_status()
        assert report.agent_id == "coder"
        assert report.state == AgentState.IDLE


class TestAgentExecution:
    """测试 Agent 任务执行"""

    @pytest.mark.asyncio
    async def test_run_single_task(self, mock_provider):
        mock_provider.responses = [
            # LLM 返回无工具调用，直接完成
            ChatResponse(
                content='完成。\n```status_report\n{"state": "completed", "will": "complete"}\n```'
            ),
        ]

        config = AgentConfig(
            id="coder",
            name="程序员",
            system_prompt="你是一个程序员。",
        )
        agent = Agent(config=config, model_provider=mock_provider)

        # 发送任务
        await agent.assign("写函数", {})

        # 收集事件
        events = []
        async for event in agent.run():
            events.append(event)
            # 收到 completed 后发送 stop
            if event.type == "agent.completed":
                await agent.inbox.put({"command": "stop"})

        event_types = [e.type for e in events]
        assert "agent.started" in event_types
        assert "agent.completed" in event_types
        assert "agent.stopped" in event_types
        assert agent.state == AgentState.COMPLETED
