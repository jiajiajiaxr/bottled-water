"""
测试 Watchdog 看门狗模块
"""

import pytest
from datetime import datetime, timedelta

from agent_runtime.runtime.watchdog import Watchdog, WatchdogConfig
from agent_runtime.core.types import AgentReport, AgentState, AgentWill, SchedulingDecision


class TestWatchdogConfig:
    """测试 WatchdogConfig"""

    def test_defaults(self):
        config = WatchdogConfig()
        assert config.max_rounds == 50
        assert config.max_idle_seconds == 300
        assert config.max_total_tokens == 500000
        assert config.deadlock_threshold == 3
        assert config.min_progress_interval == 10

    def test_custom(self):
        config = WatchdogConfig(max_rounds=10, deadlock_threshold=2)
        assert config.max_rounds == 10
        assert config.deadlock_threshold == 2
        assert config.max_idle_seconds == 300  # 默认值不变


class TestWatchdogCheckBeforeDecision:
    """测试看门狗决策前校验"""

    @pytest.fixture
    def watchdog(self):
        return Watchdog(WatchdogConfig(max_rounds=5, deadlock_threshold=2))

    def test_pass(self, watchdog):
        reports = [
            AgentReport(agent_id="a1", state=AgentState.READY, will=AgentWill.EXECUTE),
        ]
        result = watchdog.check_before_decision({}, reports)
        assert result is None
        assert watchdog.state.round_count == 1

    def test_max_rounds_exceeded(self, watchdog):
        # 模拟 6 轮（超过 max_rounds=5）
        reports = [AgentReport(agent_id="a1", state=AgentState.READY, will=AgentWill.EXECUTE)]
        for _ in range(5):
            result = watchdog.check_before_decision({}, reports)
            assert result is None

        # 第 6 轮应该触发
        result = watchdog.check_before_decision({}, reports)
        assert result is not None
        assert result.type == "watchdog_triggered"
        assert result.payload["reason"] == "max_rounds_exceeded"

    def test_deadlock_all_blocked(self, watchdog):
        # 模拟连续 3 轮所有 agent blocked
        reports = [AgentReport(agent_id="a1", state=AgentState.WAITING, will=AgentWill.BLOCKED)]

        result = watchdog.check_before_decision({}, reports)
        assert result is None  # 第 1 轮
        result = watchdog.check_before_decision({}, reports)
        assert result is None  # 第 2 轮
        result = watchdog.check_before_decision({}, reports)
        assert result is not None  # 第 3 轮，超过 deadlock_threshold=2
        assert result.payload["reason"] == "deadlock_detected"

    def test_deadlock_all_waiting(self, watchdog):
        reports = [AgentReport(agent_id="a1", state=AgentState.WAITING, will=AgentWill.WAIT)]

        result = watchdog.check_before_decision({}, reports)
        assert result is None
        result = watchdog.check_before_decision({}, reports)
        assert result is None
        result = watchdog.check_before_decision({}, reports)
        assert result is not None
        assert result.payload["reason"] == "deadlock_detected"

    def test_no_deadlock_when_progress(self, watchdog):
        blocked_reports = [AgentReport(agent_id="a1", state=AgentState.WAITING, will=AgentWill.BLOCKED)]
        active_reports = [AgentReport(agent_id="a1", state=AgentState.RUNNING, will=AgentWill.EXECUTE)]

        # 交替 blocked / active
        for _ in range(10):
            result = watchdog.check_before_decision({}, blocked_reports)
            assert result is None
            result = watchdog.check_before_decision({}, active_reports)
            assert result is None

    def test_token_budget(self):
        watchdog = Watchdog(WatchdogConfig(max_total_tokens=100))
        watchdog.state.total_tokens_used = 101
        reports = [AgentReport(agent_id="a1", state=AgentState.READY, will=AgentWill.EXECUTE)]

        result = watchdog.check_before_decision({}, reports)
        assert result is not None
        assert result.payload["reason"] == "token_budget_exhausted"


class TestWatchdogCheckAfterDecision:
    """测试看门狗决策后校验"""

    def test_pass(self):
        watchdog = Watchdog()
        decision = SchedulingDecision(decision_type="assign", target_agent_id="a1")
        result = watchdog.check_after_decision(decision)
        assert result is None

    def test_decision_loop(self):
        watchdog = Watchdog()
        decision = SchedulingDecision(decision_type="assign", target_agent_id="a1")

        # 连续 4 次相同决策
        for _ in range(3):
            result = watchdog.check_after_decision(decision)
            assert result is None

        # 第 4 次应该触发
        result = watchdog.check_after_decision(decision)
        assert result is not None
        assert result.payload["reason"] == "decision_loop"

    def test_no_loop_when_different(self):
        watchdog = Watchdog()

        for i in range(10):
            decision = SchedulingDecision(decision_type="assign", target_agent_id=f"a{i % 2}")
            result = watchdog.check_after_decision(decision)
            assert result is None


class TestWatchdogTokenTracking:
    """测试 Token 跟踪"""

    def test_add_tokens(self):
        watchdog = Watchdog()
        watchdog.add_tokens(100)
        watchdog.add_tokens(50)
        assert watchdog.state.total_tokens_used == 150

    def test_record_progress(self):
        watchdog = Watchdog()
        watchdog.state.consecutive_idle_rounds = 5
        watchdog.record_progress(tokens_used=200)
        assert watchdog.state.total_tokens_used == 200
        assert watchdog.state.consecutive_idle_rounds == 0


class TestWatchdogGetStatus:
    """测试状态查询"""

    def test_get_status(self):
        watchdog = Watchdog(WatchdogConfig(max_rounds=10))
        status = watchdog.get_status()
        assert status["round_count"] == 0
        assert status["total_tokens_used"] == 0
        assert status["consecutive_idle_rounds"] == 0
        assert status["config"]["max_rounds"] == 10
        assert "started_at" in status
