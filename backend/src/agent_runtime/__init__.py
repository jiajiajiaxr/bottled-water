"""
agent_runtime - 多智能体运行时

纯 Python 库，不依赖任何 Web 框架。
可独立使用，也可被 FastAPI/Flask/其他框架集成。

使用示例：
    from agent_runtime import Session, AgentConfig, TechLeadScheduler
    from model_provider import create_provider, ModelConfig

    provider = create_provider(ModelConfig(provider="ark", model="ep-xxx", api_key="xxx"))

    session = Session.create(
        agents=[AgentConfig(id="coder", name="程序员", system_prompt="...")],
        scheduler=TechLeadScheduler(),
        model_provider=provider,
    )

    async for event in session.run("实现登录功能"):
        print(event)
"""

from .core.types import (
    AgentConfig,
    AgentState,
    AgentWill,
    AgentReport,
    SchedulingDecision,
    Event,
    Message,
    ToolCall,
    ToolResult,
)
from .core.interfaces import PersistenceBackend, EventSink, ToolExecutor
from .runtime.session import Session
from .runtime.watchdog import Watchdog, WatchdogConfig
from .strategies.base import Scheduler
from .strategies.tech_lead import TechLeadScheduler
from .strategies.single_agent import SingleAgentScheduler
from .context.blackboard import BlackboardManager
from .context.agent_ctx import AgentContextManager, AgentContext
from .tools.registry import ToolRegistry
from .tools.executor import ToolExecutorImpl

__all__ = [
    # 核心类型
    "AgentConfig",
    "AgentState",
    "AgentWill",
    "AgentReport",
    "SchedulingDecision",
    "Event",
    "Message",
    "ToolCall",
    "ToolResult",
    # 接口
    "PersistenceBackend",
    "EventSink",
    "ToolExecutor",
    # 运行时
    "Session",
    "Watchdog",
    "WatchdogConfig",
    # 调度策略
    "Scheduler",
    "TechLeadScheduler",
    "SingleAgentScheduler",
    # 上下文管理
    "BlackboardManager",
    "AgentContextManager",
    "AgentContext",
    # 工具
    "ToolRegistry",
    "ToolExecutorImpl",
]
