"""
测试核心类型定义
"""

from datetime import datetime

from agent_runtime.core.types import (
    AgentConfig, AgentState, AgentWill, AgentReport,
    SchedulingDecision, Event, Message, ToolCall, ToolResult,
)


class TestAgentConfig:
    """测试 AgentConfig"""

    def test_basic_creation(self):
        config = AgentConfig(
            id="coder",
            name="程序员",
            system_prompt="你是一个程序员。",
        )
        assert config.id == "coder"
        assert config.name == "程序员"
        assert config.system_prompt == "你是一个程序员。"
        assert config.role == "worker"  # 默认值
        assert config.tools == []  # 默认值
        assert config.model_config == {}  # 默认值

    def test_with_tools(self):
        config = AgentConfig(
            id="coder",
            name="程序员",
            system_prompt="你是一个程序员。",
            role="leader",
            tools=["file_read", "file_write"],
            model_config={"temperature": 0.5},
        )
        assert config.role == "leader"
        assert config.tools == ["file_read", "file_write"]
        assert config.model_config == {"temperature": 0.5}


class TestAgentState:
    """测试 AgentState 枚举"""

    def test_enum_values(self):
        assert AgentState.IDLE == "idle"
        assert AgentState.READY == "ready"
        assert AgentState.RUNNING == "running"
        assert AgentState.WAITING == "waiting"
        assert AgentState.COMPLETED == "completed"
        assert AgentState.FAILED == "failed"


class TestAgentWill:
    """测试 AgentWill 枚举"""

    def test_enum_values(self):
        assert AgentWill.EXECUTE == "execute"
        assert AgentWill.WAIT == "wait"
        assert AgentWill.DELEGATE == "delegate"
        assert AgentWill.COMPLETE == "complete"
        assert AgentWill.BLOCKED == "blocked"


class TestAgentReport:
    """测试 AgentReport"""

    def test_basic_creation(self):
        report = AgentReport(
            agent_id="coder",
            state=AgentState.READY,
            will=AgentWill.EXECUTE,
        )
        assert report.agent_id == "coder"
        assert report.state == "ready"
        assert report.will == "execute"
        assert report.rationale == ""  # 默认值
        assert report.blockers == []  # 默认值
        assert report.priority == 0  # 默认值
        assert report.confidence == 1.0  # 默认值

    def test_full_creation(self):
        report = AgentReport(
            agent_id="coder",
            state=AgentState.COMPLETED,
            will=AgentWill.COMPLETE,
            target_task="实现登录功能",
            blockers=["缺少 API 文档"],
            priority=1,
            confidence=0.95,
            rationale="任务已完成",
            expected_duration=30,
        )
        assert report.target_task == "实现登录功能"
        assert report.blockers == ["缺少 API 文档"]
        assert report.priority == 1
        assert report.confidence == 0.95
        assert report.rationale == "任务已完成"
        assert report.expected_duration == 30


class TestSchedulingDecision:
    """测试 SchedulingDecision"""

    def test_basic_creation(self):
        decision = SchedulingDecision(
            decision_type="assign",
            target_agent_id="coder",
            task_description="实现登录功能",
        )
        assert decision.decision_type == "assign"
        assert decision.target_agent_id == "coder"
        assert decision.task_description == "实现登录功能"
        assert decision.rationale == ""  # 默认值
        assert decision.requires_verification is False  # 默认值
        assert decision.verification_agents == []  # 默认值


class TestEvent:
    """测试 Event"""

    def test_basic_creation(self):
        event = Event(
            type="system.agent_started",
            payload={"agent_id": "coder"},
        )
        assert event.type == "system.agent_started"
        assert event.payload == {"agent_id": "coder"}
        assert isinstance(event.timestamp, datetime)


class TestMessage:
    """测试 Message"""

    def test_basic_creation(self):
        msg = Message(
            id="msg_1",
            conversation_id="conv_1",
            agent_id="coder",
            content="你好",
            role="user",
        )
        assert msg.id == "msg_1"
        assert msg.conversation_id == "conv_1"
        assert msg.agent_id == "coder"
        assert msg.content == "你好"
        assert msg.role == "user"
        assert msg.metadata == {}  # 默认值
        assert isinstance(msg.created_at, datetime)


class TestToolCall:
    """测试 ToolCall"""

    def test_basic_creation(self):
        call = ToolCall(
            tool_name="file_read",
            parameters={"path": "/tmp/test.txt"},
            call_id="call_1",
        )
        assert call.tool_name == "file_read"
        assert call.parameters == {"path": "/tmp/test.txt"}
        assert call.call_id == "call_1"


class TestToolResult:
    """测试 ToolResult"""

    def test_success(self):
        result = ToolResult(
            call_id="call_1",
            success=True,
            result="file content",
        )
        assert result.call_id == "call_1"
        assert result.success is True
        assert result.result == "file content"
        assert result.error is None

    def test_failure(self):
        result = ToolResult(
            call_id="call_1",
            success=False,
            result=None,
            error="文件不存在",
        )
        assert result.success is False
        assert result.result is None
        assert result.error == "文件不存在"
