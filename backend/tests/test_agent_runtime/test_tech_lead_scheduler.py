"""
测试 TechLeadScheduler

覆盖：
- 回退策略
- LLM 决策解析
- 冲突解决
"""

import pytest

from agent_runtime.strategies.tech_lead import TechLeadScheduler
from agent_runtime.core.types import AgentConfig, AgentReport, AgentState, AgentWill
from model_provider import ChatResponse

class TestTechLeadSchedulerFallback:
    """测试回退策略"""

    @pytest.fixture
    def scheduler(self):
        return TechLeadScheduler()

    @pytest.mark.asyncio
    async def test_fallback_ready_agent(self, scheduler):
        reports = [
            AgentReport(agent_id="coder", state=AgentState.READY, will=AgentWill.EXECUTE),
            AgentReport(agent_id="reviewer", state=AgentState.WAITING, will=AgentWill.WAIT),
        ]
        decision = await scheduler.make_decision({}, reports, {})
        assert decision.decision_type == "assign"
        assert decision.target_agent_id == "coder"
        assert "回退策略" in decision.rationale

    @pytest.mark.asyncio
    async def test_fallback_all_completed(self, scheduler):
        reports = [
            AgentReport(agent_id="coder", state=AgentState.COMPLETED, will=AgentWill.COMPLETE),
        ]
        decision = await scheduler.make_decision({}, reports, {})
        assert decision.decision_type == "complete"

    @pytest.mark.asyncio
    async def test_fallback_no_ready(self, scheduler):
        reports = [
            AgentReport(agent_id="coder", state=AgentState.WAITING, will=AgentWill.WAIT),
        ]
        decision = await scheduler.make_decision({}, reports, {})
        assert decision.decision_type == "wait"


class TestTechLeadSchedulerLLM:
    """测试 LLM 调度决策"""

    @pytest.fixture
    def scheduler(self, mock_provider):
        return TechLeadScheduler(
            agents={
                "coder": AgentConfig(id="coder", name="程序员", system_prompt="写代码"),
                "reviewer": AgentConfig(id="reviewer", name="审查员", system_prompt="审查"),
            },
            model_provider=mock_provider,
        )

    @pytest.mark.asyncio
    async def test_llm_decision_assign(self, scheduler, mock_provider):
        mock_provider.responses = [
            ChatResponse(content='{"decision_type": "assign", "target_agent_id": "coder", "task_description": "实现功能", "rationale": "程序员适合"}'),
        ]

        reports = [
            AgentReport(agent_id="coder", state=AgentState.READY, will=AgentWill.EXECUTE),
        ]
        decision = await scheduler.make_decision(
            {"recent_history": [], "kv_state": {}},
            reports,
            {"round": 1, "session_id": "s1", "current_task": "写代码"},
        )

        assert decision.decision_type == "assign"
        assert decision.target_agent_id == "coder"
        assert decision.task_description == "实现功能"
        assert mock_provider.call_count == 1

    @pytest.mark.asyncio
    async def test_llm_decision_complete(self, scheduler, mock_provider):
        mock_provider.responses = [
            ChatResponse(content='{"decision_type": "complete", "rationale": "全部完成"}'),
        ]

        reports = [AgentReport(agent_id="coder", state=AgentState.COMPLETED, will=AgentWill.COMPLETE)]
        decision = await scheduler.make_decision({}, reports, {})

        assert decision.decision_type == "complete"

    @pytest.mark.asyncio
    async def test_llm_failure_fallback(self, scheduler, mock_provider):
        """LLM 调用失败时回退到简单策略"""
        mock_provider.responses = []  # 空列表会导致 IndexError

        reports = [
            AgentReport(agent_id="coder", state=AgentState.READY, will=AgentWill.EXECUTE),
        ]
        # 将 model_provider 设为 None 模拟无模型情况
        scheduler.model_provider = None
        decision = await scheduler.make_decision({}, reports, {})
        assert decision.decision_type == "assign"


class TestTechLeadSchedulerParse:
    """测试 JSON 解析"""

    def test_parse_plain_json(self):
        scheduler = TechLeadScheduler()
        data = scheduler._parse_decision_json('{"decision_type": "assign", "target_agent_id": "a1"}')
        assert data["decision_type"] == "assign"
        assert data["target_agent_id"] == "a1"

    def test_parse_json_code_block(self):
        scheduler = TechLeadScheduler()
        data = scheduler._parse_decision_json('```json\n{"decision_type": "wait"}\n```')
        assert data["decision_type"] == "wait"

    def test_parse_invalid_json(self):
        scheduler = TechLeadScheduler()
        data = scheduler._parse_decision_json("不是 JSON")
        assert data["decision_type"] == "wait"
        assert "无法解析" in data["rationale"]


class TestTechLeadSchedulerResolveConflict:
    """测试冲突解决"""

    @pytest.mark.asyncio
    async def test_resolve_conflict_fallback(self):
        scheduler = TechLeadScheduler()
        reports = [
            AgentReport(agent_id="a1", state=AgentState.READY, will=AgentWill.EXECUTE),
            AgentReport(agent_id="a2", state=AgentState.READY, will=AgentWill.EXECUTE),
        ]
        decision = await scheduler.resolve_conflict("resource_conflict", reports, {})
        assert decision.decision_type == "assign"
        assert decision.target_agent_id == "a1"
