"""
运行时核心类型

使用标准库 dataclasses，零框架依赖。
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum


class AgentState(str, Enum):
    """Agent 运行状态"""
    IDLE = "idle"
    READY = "ready"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentWill(str, Enum):
    """Agent 意图"""
    EXECUTE = "execute"
    WAIT = "wait"
    DELEGATE = "delegate"
    COMPLETE = "complete"
    BLOCKED = "blocked"


@dataclass
class AgentConfig:
    """Agent 配置"""
    id: str
    name: str
    system_prompt: str
    role: str = "worker"  # "leader" | "worker" | "verifier"
    model_config: Dict[str, Any] = field(default_factory=dict)
    tools: List[str] = field(default_factory=list)


@dataclass
class AgentReport:
    """Agent 状态报告"""
    agent_id: str
    state: AgentState
    will: AgentWill
    target_task: Optional[str] = None
    blockers: List[str] = field(default_factory=list)
    priority: int = 0
    confidence: float = 1.0
    rationale: str = ""
    expected_duration: Optional[int] = None


@dataclass
class SchedulingDecision:
    """调度决策"""
    decision_type: str  # "assign" | "parallel" | "wait" | "escalate" | "user_input"
    target_agent_id: Optional[str] = None
    task_description: str = ""
    rationale: str = ""
    requires_verification: bool = False
    verification_agents: List[str] = field(default_factory=list)


@dataclass
class Message:
    """运行时消息"""
    id: str
    conversation_id: str
    agent_id: Optional[str]
    content: str
    role: str  # "user" | "assistant" | "system" | "tool"
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Event:
    """运行时事件"""
    type: str
    payload: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ToolCall:
    """工具调用"""
    tool_name: str
    parameters: Dict[str, Any]
    call_id: str


@dataclass
class ToolResult:
    """工具执行结果"""
    call_id: str
    success: bool
    result: Any
    error: Optional[str] = None
