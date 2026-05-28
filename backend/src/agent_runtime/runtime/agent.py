"""
Agent 自持实体

从贫血函数到自持实体：
- 持有 config、context、model
- 自己负责推理循环
- 通过 inbox/outbox 与主循环异步通信
- 内部维护显式状态机
- 支持步进执行（每步后让出控制权）

与旧架构的关系：
- AgentLoop 退化为 Agent 的内部引擎
- Orchestrator 通过 inbox 发送指令，通过 outbox 接收报告
"""

import asyncio
from typing import Dict, Any, Optional, AsyncIterator

from model_provider.core.interfaces import BaseModelProvider

from common.logger import get_logger
from ..core.types import AgentConfig, AgentState, AgentWill, AgentReport, Event
from ..core.interfaces import ToolExecutor
from ..context.agent_ctx import AgentContext
from .agent_loop import AgentLoop

logger = get_logger(__name__)


class Agent:
    """Agent 自持实体

    每个 Agent 是一个持续运行的协程，通过 inbox/outbox 与 Orchestrator 通信。
    内部状态机：IDLE → READY → RUNNING → WAITING → COMPLETED
                           ↑_____________|
    """

    def __init__(
        self,
        config: AgentConfig,
        model_provider: BaseModelProvider,
        tool_executor: Optional[ToolExecutor] = None,
    ):
        self.config = config
        self.model = model_provider
        self.tool_executor = tool_executor

        # 内部引擎
        self._loop = AgentLoop(config, model_provider)

        # 状态机
        self._state = AgentState.IDLE
        self._current_task: Optional[str] = None

        # 上下文
        self.ctx = AgentContext(agent_id=config.id, conversation_id="")
        self.ctx.system_prompt = config.system_prompt

        # 通信队列
        self.inbox: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()
        self.outbox: asyncio.Queue[Dict[str, Any]] = asyncio.Queue()

    @property
    def id(self) -> str:
        return self.config.id

    @property
    def state(self) -> AgentState:
        return self._state

    @property
    def current_task(self) -> Optional[str]:
        return self._current_task

    def _set_state(self, new_state: AgentState):
        if self._state != new_state:
            logger.debug(
                "Agent 状态变更",
                agent_id=self.id,
                old=self._state.value,
                new=new_state.value,
            )
            self._state = new_state

    # --- 公共接口 ---

    async def assign(self, task: str, blackboard_view: dict, conversation_id: str = ""):
        """通过 inbox 发送指派指令"""
        await self.inbox.put(
            {
                "command": "assign",
                "task": task,
                "blackboard_view": blackboard_view,
                "conversation_id": conversation_id,
            }
        )

    async def pause(self):
        """通过 inbox 发送暂停指令"""
        await self.inbox.put({"command": "pause"})

    async def report_status(self) -> AgentReport:
        """通过 inbox 请求状态报告"""
        await self.inbox.put({"command": "report_status"})
        # 等待 outbox 中的报告
        msg = await self._wait_for_outbox("status_report", timeout=5.0)
        return msg["report"] if msg else self._default_report()

    # --- 主循环 ---

    async def run(self) -> AsyncIterator[Event]:
        """Agent 主循环（持续运行直到收到 stop 指令）

        Yields:
            状态变更事件、工具调用事件等
        """
        self._set_state(AgentState.IDLE)
        logger.info("Agent 主循环启动", agent_id=self.id)

        while True:
            # 1. 检查 inbox 是否有新指令
            try:
                msg = await asyncio.wait_for(self.inbox.get(), timeout=0.1)
            except asyncio.TimeoutError:
                msg = None

            if msg:
                command = msg.get("command")

                if command == "assign":
                    self._current_task = msg["task"]
                    self.ctx.conversation_id = msg.get("conversation_id", "")
                    self._set_state(AgentState.READY)

                    # 执行单轮任务
                    async for event in self._execute_task(
                        msg["task"], msg.get("blackboard_view", {})
                    ):
                        yield event

                elif command == "pause":
                    self._set_state(AgentState.WAITING)
                    yield Event(
                        type="agent.paused",
                        payload={"agent_id": self.id, "state": self._state.value},
                        source=f"agent:{self.id}",
                    )

                elif command == "report_status":
                    await self.outbox.put(
                        {
                            "type": "status_report",
                            "report": self._build_status_report(),
                        }
                    )

                elif command == "stop":
                    self._set_state(AgentState.COMPLETED)
                    yield Event(
                        type="agent.stopped",
                        payload={"agent_id": self.id},
                        source=f"agent:{self.id}",
                    )
                    break

            # 让出控制权
            await asyncio.sleep(0)

        logger.info("Agent 主循环结束", agent_id=self.id)

    # --- 内部执行 ---

    async def _execute_task(self, task: str, blackboard_view: dict) -> AsyncIterator[Event]:
        """执行单轮任务（步进模式）"""
        self._set_state(AgentState.RUNNING)

        yield Event(
            type="agent.started",
            payload={"agent_id": self.id, "task": task},
            source=f"agent:{self.id}",
        )

        try:
            # 使用 AgentLoop 执行（内部已经分步，但一次性完成）
            # TODO: 未来将 AgentLoop 完全拆分为步进执行
            result = await self._loop.run(
                task=task,
                blackboard_view=blackboard_view,
                tool_executor=self.tool_executor,
                agent_ctx=self.ctx,
                emit_event=self._on_agent_loop_event,
            )

            status_report = result["status_report"]

            # 自判断 will
            self._set_state(status_report.state)

            yield Event(
                type="agent.completed",
                payload={
                    "agent_id": self.id,
                    "work_product": result["work_product"],
                    "status_report": {
                        "state": status_report.state,
                        "will": status_report.will.value,
                        "rationale": status_report.rationale,
                    },
                },
                source=f"agent:{self.id}",
            )

            # 发送状态报告到 outbox
            await self.outbox.put(
                {
                    "type": "task_completed",
                    "report": status_report,
                    "work_product": result["work_product"],
                }
            )

        except Exception as e:
            self._set_state(AgentState.FAILED)
            logger.error("Agent 执行失败", agent_id=self.id, error=str(e))
            yield Event(
                type="agent.failed",
                payload={"agent_id": self.id, "error": str(e)},
                source=f"agent:{self.id}",
            )

    async def _on_agent_loop_event(self, event: Event):
        """转发 AgentLoop 内部事件"""
        # 事件已经由 AgentLoop 构建好，直接通过 outbox 转发
        pass

    async def _wait_for_outbox(
        self, msg_type: str, timeout: float = 5.0
    ) -> Optional[Dict[str, Any]]:
        """等待 outbox 中特定类型的消息"""
        try:
            msg = await asyncio.wait_for(self.outbox.get(), timeout=timeout)
            if msg.get("type") == msg_type:
                return msg
        except asyncio.TimeoutError:
            pass
        return None

    def _build_status_report(self) -> AgentReport:
        """构建当前状态报告"""
        return AgentReport(
            agent_id=self.id,
            state=self._state,
            will=AgentWill.EXECUTE if self._state == AgentState.RUNNING else AgentWill.WAIT,
            rationale=f"Agent 当前状态: {self._state.value}",
        )

    def _default_report(self) -> AgentReport:
        """默认报告"""
        return AgentReport(
            agent_id=self.id,
            state=self._state,
            will=AgentWill.WAIT,
            rationale="无状态报告",
        )
