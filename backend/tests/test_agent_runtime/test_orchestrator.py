"""
测试 Orchestrator

覆盖调度循环的核心逻辑。
"""

import pytest

from agent_runtime.runtime.orchestrator import Orchestrator
from agent_runtime.runtime.watchdog import WatchdogConfig
from agent_runtime.core.types import (
    AgentConfig, AgentState, AgentWill, AgentReport, Event, SchedulingDecision,
)
from agent_runtime.strategies.base import Scheduler


class SimpleScheduler(Scheduler):
    """简单的测试调度器"""

    def __init__(self, decisions=None):
        super().__init__()
        self.decisions = decisions or []
        self.call_count = 0

    async def make_decision(self, blackboard, agent_reports, conversation_context):
        self.call_count += 1
        if self.decisions:
            idx = min(self.call_count - 1, len(self.decisions) - 1)
            return self.decisions[idx]
        # 默认：选择第一个 ready 的 agent
        for report in agent_reports:
            if report.state == "ready":
                return SchedulingDecision(
                    decision_type="assign",
                    target_agent_id=report.agent_id,
                    task_description="执行任务",
                )
        return SchedulingDecision(decision_type="complete")

    async def resolve_conflict(self, conflict_type, conflicting_reports, blackboard):
        return SchedulingDecision(
            decision_type="assign",
            target_agent_id=conflicting_reports[0].agent_id,
        )


@pytest.fixture
def sample_agents():
    return {
        "coder": AgentConfig(id="coder", name="程序员", system_prompt="你是一个程序员。"),
        "reviewer": AgentConfig(id="reviewer", name="审查员", system_prompt="你是一个审查员。"),
    }


class TestOrchestratorInit:
    """测试 Orchestrator 初始化"""

    def test_init(self, sample_agents, mock_provider):
        scheduler = SimpleScheduler()
        orch = Orchestrator(
            session_id="sess_1",
            agents=sample_agents,
            scheduler=scheduler,
            model_provider=mock_provider,
        )
        assert orch.session_id == "sess_1"
        assert orch.status == "idle"
        assert orch.round_num == 0
        assert len(orch.agents) == 2


class TestOrchestratorRun:
    """测试 Orchestrator 运行"""

    @pytest.fixture
    def scheduler(self):
        return SimpleScheduler([
            SchedulingDecision(decision_type="assign", target_agent_id="coder", task_description="写代码"),
            SchedulingDecision(decision_type="complete"),
        ])

    @pytest.fixture
    def orch(self, sample_agents, scheduler, mock_provider):
        return Orchestrator(
            session_id="sess_1",
            agents=sample_agents,
            scheduler=scheduler,
            model_provider=mock_provider,
        )

    @pytest.mark.asyncio
    async def test_run_basic(self, orch, mock_provider):
        """测试基本运行流程"""
        mock_provider.responses = [
            ChatResponse(content="代码写好了。\n```status_report\n{\"state\": \"completed\", \"will\": \"complete\"}\n```"),
        ]

        events = []
        async for event in orch.run("实现登录功能"):
            events.append(event)

        # 应该产生 session_started, round_started, scheduling_decision, agent_started, agent_completed, session_completed
        event_types = [e.type for e in events]
        assert "session_started" in event_types
        assert "session_completed" in event_types
        assert "scheduling_decision" in event_types
        assert orch.status == "completed"

    @pytest.mark.asyncio
    async def test_run_with_persistence(self, orch, mock_provider, mock_persistence):
        """测试带持久化的运行"""
        mock_provider.responses = [
            ChatResponse(content="完成。\n```status_report\n{\"state\": \"completed\", \"will\": \"complete\"}\n```"),
        ]
        orch.persistence = mock_persistence

        events = []
        async for event in orch.run("任务"):
            events.append(event)

        # 验证 Blackboard 被保存
        assert "sess_1" in mock_persistence.blackboards
        bb = mock_persistence.blackboards["sess_1"]
        assert bb["conversation_id"] == "sess_1"
        assert len(bb["raw_history"]) > 0

    @pytest.mark.asyncio
    async def test_run_watchdog_max_rounds(self, sample_agents, mock_provider):
        """测试看门狗轮数上限"""
        # 调度器总是返回 assign，不会 complete
        scheduler = SimpleScheduler([
            SchedulingDecision(decision_type="assign", target_agent_id="coder"),
        ])
        orch = Orchestrator(
            session_id="sess_1",
            agents=sample_agents,
            scheduler=scheduler,
            model_provider=mock_provider,
            watchdog_config=WatchdogConfig(max_rounds=3),
        )

        mock_provider.responses = [
            ChatResponse(content="工作中。\n```status_report\n{\"state\": \"running\", \"will\": \"execute\"}\n```"),
        ] * 5

        events = []
        async for event in orch.run("任务"):
            events.append(event)

        watchdog_events = [e for e in events if e.type == "watchdog_triggered"]
        assert len(watchdog_events) >= 1
        assert watchdog_events[0].payload["reason"] == "max_rounds_exceeded"

    @pytest.mark.asyncio
    async def test_run_with_event_sink(self, orch, mock_provider, mock_event_sink):
        """测试事件接收器"""
        mock_provider.responses = [
            ChatResponse(content="完成。\n```status_report\n{\"state\": \"completed\", \"will\": \"complete\"}\n```"),
        ]
        orch.event_sink = mock_event_sink

        async for _ in orch.run("任务"):
            pass

        assert len(mock_event_sink.events) > 0


class TestOrchestratorStatus:
    """测试状态查询"""

    def test_get_status(self, sample_agents, mock_provider):
        scheduler = SimpleScheduler()
        orch = Orchestrator(
            session_id="sess_1",
            agents=sample_agents,
            scheduler=scheduler,
            model_provider=mock_provider,
        )
        status = orch.get_status()
        assert status["session_id"] == "sess_1"
        assert status["status"] == "idle"
        assert status["round"] == 0
        assert len(status["agents"]) == 2
        assert "watchdog" in status


class TestOrchestratorUserInput:
    """测试用户中途输入"""

    @pytest.mark.asyncio
    async def test_handle_user_input(self, sample_agents, mock_provider):
        scheduler = SimpleScheduler([
            SchedulingDecision(decision_type="complete"),
        ])
        orch = Orchestrator(
            session_id="sess_1",
            agents=sample_agents,
            scheduler=scheduler,
            model_provider=mock_provider,
        )

        events = []
        async for event in orch.handle_user_input("新消息"):
            events.append(event)

        assert events[0].type == "user_input_queued"
        assert orch._user_input_queue == ["新消息"]
