"""
编排器 - 会话级调度循环

负责：
- 初始化 Blackboard 和 Agent 上下文
- 多轮调度循环：收集报告 → 看门狗校验 → 调度器决策 → 执行 → 归档
- 看门狗集成
- 事件发射
- 用户中途输入处理
"""

import asyncio
from typing import Dict, List, Optional, AsyncIterator, Tuple
from datetime import datetime

from model_provider.core.interfaces import BaseModelProvider

from common.logger import get_logger
from ..core.types import (
    AgentConfig,
    AgentReport,
    AgentState,
    AgentWill,
    Event,
    Message,
    SchedulingDecision,
)
from ..core.interfaces import PersistenceBackend, ToolExecutor
from ..strategies.base import Scheduler
from ..context.blackboard import BlackboardManager
from ..context.agent_ctx import AgentContextManager
from .agent_loop import AgentLoop
from .watchdog import Watchdog, WatchdogConfig

logger = get_logger(__name__)


class Orchestrator:
    """编排器"""

    def __init__(
        self,
        session_id: str,
        agents: Dict[str, AgentConfig],
        scheduler: Scheduler,
        model_provider: BaseModelProvider,
        persistence: Optional[PersistenceBackend] = None,
        tool_executor: Optional[ToolExecutor] = None,
        watchdog_config: Optional[WatchdogConfig] = None,
    ):
        self.session_id = session_id
        self.agents = agents
        self.scheduler = scheduler
        self.model_provider = model_provider
        self.persistence = persistence
        self.tool_executor = tool_executor
        self.watchdog = Watchdog(watchdog_config)

        # 上下文管理
        self.blackboard_mgr = BlackboardManager(persistence=persistence)
        self.agent_ctx_mgr = AgentContextManager()

        # 状态
        self.status = "idle"  # idle | running | paused | completed | failed
        self.round_num = 0
        self._user_input_queue: asyncio.Queue[str] = asyncio.Queue()
        self._agent_loops: Dict[str, AgentLoop] = {}
        self._pending_agent_reports: Dict[str, AgentReport] = {}

    async def run(self, user_message: str) -> AsyncIterator[Event]:
        """运行会话调度循环"""
        self.status = "running"
        logger.info("调度循环开始", session_id=self.session_id, agents=list(self.agents.keys()))

        # 1. 初始化
        await self._initialize(user_message)

        yield Event(
            type="system.session_started",
            payload={
                "session_id": self.session_id,
                "agents": [
                    {"id": a.id, "name": a.name, "role": a.role} for a in self.agents.values()
                ],
            },
        )

        # 2. 主调度循环
        try:
            async for event in self._scheduling_loop(user_message):
                yield event
        except Exception as e:
            self.status = "failed"
            logger.error("调度循环异常", session_id=self.session_id, error=str(e), exc_info=True)
            yield Event(
                type="system.session_error",
                payload={
                    "session_id": self.session_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                },
            )
            raise

        # 3. 结束
        self.status = "completed"
        logger.info("调度循环结束", session_id=self.session_id, rounds=self.round_num)
        yield Event(
            type="system.session_completed",
            payload={
                "session_id": self.session_id,
                "rounds": self.round_num,
                "watchdog_status": self.watchdog.get_status(),
            },
        )

    async def _initialize(self, user_message: str):
        """初始化 Blackboard 和 Agent 上下文"""
        # 重置调度器状态（支持 Session 复用场景）
        self.scheduler.reset()

        # 重置本地状态
        self.round_num = 0
        self._pending_agent_reports.clear()
        self._agent_loops.clear()
        self._user_input_queue = asyncio.Queue()

        # 创建/加载 Blackboard
        blackboard = await self.blackboard_mgr.create(self.session_id)
        if self.persistence:
            await self.persistence.save_blackboard(self.session_id, blackboard)

        # 记录用户消息到 Blackboard
        await self.blackboard_mgr.append_history(
            self.session_id,
            {
                "type": "user_message",
                "content": user_message,
                "round": 0,
            },
        )

        # 初始化各 Agent 上下文
        for agent_id, agent in self.agents.items():
            self.agent_ctx_mgr.initialize(
                agent_id=agent_id,
                conversation_id=self.session_id,
                system_prompt=agent.system_prompt,
                role_config={"name": agent.name, "role": agent.role, "tools": agent.tools},
            )
            # 创建 AgentLoop 实例
            self._agent_loops[agent_id] = AgentLoop(
                agent_config=agent,
                model_provider=self.model_provider,
                use_streaming=True,
            )

        # 保存用户消息
        if self.persistence:
            await self.persistence.save_message(
                Message(
                    id=f"msg_{self.session_id}_user_{datetime.utcnow().timestamp()}",
                    conversation_id=self.session_id,
                    agent_id=None,
                    content=user_message,
                    role="user",
                )
            )

    async def _scheduling_loop(self, initial_task: str) -> AsyncIterator[Event]:
        """调度循环核心"""
        current_task = initial_task

        while self.status == "running":
            self.round_num += 1
            logger.info("调度轮开始", session_id=self.session_id, round=self.round_num)

            # --- 0. 检查用户中途输入 ---
            try:
                user_input = self._user_input_queue.get_nowait()
                await self._handle_user_input_to_blackboard(user_input)
                current_task = user_input  # 用户输入成为新任务
                yield Event(type="user.input_received", payload={"content": user_input})
            except asyncio.QueueEmpty:
                pass

            # --- 1. 获取 Blackboard 视图 ---
            blackboard = await self.blackboard_mgr.get(self.session_id) or {}
            blackboard_view = self._build_blackboard_view(blackboard)

            # --- 2. 收集 Agent 报告 ---
            reports = self._collect_reports()
            # 只清空已完成/失败的报告，保留未完成状态的报告
            self._pending_agent_reports = {
                aid: r
                for aid, r in self._pending_agent_reports.items()
                if r.state not in ("completed", "failed")
            }

            yield Event(
                type="system.round_started",
                payload={
                    "round": self.round_num,
                    "session_id": self.session_id,
                    "agent_reports": [
                        {"agent_id": r.agent_id, "state": r.state, "will": r.will.value}
                        for r in reports
                    ],
                },
            )

            # --- 3. 看门狗前置校验 ---
            watchdog_event = self.watchdog.check_before_decision(blackboard_view, reports)

            if watchdog_event:
                yield Event(type="control.watchdog_triggered", payload=watchdog_event.payload)
                self.status = "completed"
                return

            # --- 4. 调度器决策 ---
            decision = await self.scheduler.make_decision(
                blackboard=blackboard_view,
                agent_reports=reports,
                conversation_context={
                    "session_id": self.session_id,
                    "round": self.round_num,
                    "current_task": current_task,
                    "agent_count": len(self.agents),
                },
            )
            logger.info(
                "调度决策",
                session_id=self.session_id,
                round=self.round_num,
                decision=decision.decision_type,
                target=decision.target_agent_id,
            )

            yield Event(
                type="control.scheduling_decision",
                payload={
                    "round": self.round_num,
                    "decision": decision.decision_type,
                    "target": decision.target_agent_id,
                    "task": decision.task_description,
                    "rationale": decision.rationale,
                },
            )

            # --- 5. 看门狗后置校验 ---
            watchdog_event = self.watchdog.check_after_decision(decision)
            if watchdog_event:
                yield Event(type="control.watchdog_triggered", payload=watchdog_event.payload)
                self.status = "completed"
                return

            # --- 6. 执行决策 ---
            should_continue, events = await self._execute_decision(
                decision, current_task, blackboard_view
            )
            for event in events:
                yield event
            if not should_continue:
                break

            # --- 7. 判断循环是否继续 ---
            all_completed = all(r.will.value == "complete" for r in reports)
            if all_completed and len(reports) == len(self.agents):
                logger.info("所有 Agent 已完成，结束调度循环", session_id=self.session_id)
                break

            logger.info("调度轮结束", session_id=self.session_id, round=self.round_num)

    async def _execute_decision(
        self,
        decision: SchedulingDecision,
        current_task: str,
        blackboard_view: dict,
    ) -> Tuple[bool, List[Event]]:
        """
        执行调度决策。

        Returns:
            (是否继续循环, 事件列表)
        """
        decision_type = decision.decision_type
        events: List[Event] = []

        if decision_type == "assign":
            cont, evs = await self._execute_assign(decision, current_task, blackboard_view)
            return cont, evs

        if decision_type == "parallel":
            cont, evs = await self._execute_parallel(decision, current_task, blackboard_view)
            return cont, evs

        if decision_type == "wait":
            logger.info("调度器决策等待", session_id=self.session_id)
            if self._user_input_queue.empty():
                return False, events
            return True, events

        if decision_type == "escalate":
            logger.info("调度器决策升级", session_id=self.session_id, rationale=decision.rationale)
            events.append(
                Event(
                    type="control.escalation",
                    payload={
                        "rationale": decision.rationale,
                        "target": decision.target_agent_id,
                    },
                )
            )
            return True, events

        if decision_type == "user_input":
            logger.info(
                "调度器请求用户输入", session_id=self.session_id, rationale=decision.rationale
            )
            events.append(
                Event(
                    type="user.waiting_for_input",
                    payload={
                        "rationale": decision.rationale,
                    },
                )
            )
            return False, events

        if decision_type == "complete":
            logger.info("调度器决策完成", session_id=self.session_id)
            return False, events

        logger.warning("未知决策类型", session_id=self.session_id, decision_type=decision_type)
        return True, events

    async def _execute_assign(
        self,
        decision: SchedulingDecision,
        current_task: str,
        blackboard_view: dict,
    ) -> Tuple[bool, List[Event]]:
        """执行指派决策：让目标 Agent 执行任务"""
        events: List[Event] = []
        agent_id = decision.target_agent_id
        if not agent_id or agent_id not in self.agents:
            logger.error("指派目标无效", session_id=self.session_id, target=agent_id)
            return True, events

        agent = self.agents[agent_id]
        agent_loop = self._agent_loops[agent_id]
        task = decision.task_description or current_task

        logger.info("Agent 执行开始", session_id=self.session_id, agent_id=agent_id, task=task[:50])

        # 构建 Agent 上下文
        agent_ctx = self.agent_ctx_mgr.get(agent_id, self.session_id)
        agent_ctx.add("task", task)
        agent_ctx.current_round = self.round_num
        agent_ctx.current_task = task

        events.append(
            Event(
                type="system.agent_started",
                payload={
                    "round": self.round_num,
                    "agent_id": agent_id,
                    "agent_name": agent.name,
                    "task": task,
                },
            )
        )

        try:
            # 收集 AgentLoop 内部事件
            agent_internal_events: List[Event] = []

            async def _emit_agent_event(event: Event):
                agent_internal_events.append(event)

            # 执行 Agent 循环（传入 AgentContext 保持记忆 + 事件回调）
            result = await agent_loop.run(
                task=task,
                blackboard_view=blackboard_view,
                tool_executor=self.tool_executor,
                agent_ctx=agent_ctx,
                emit_event=_emit_agent_event,
            )

            # 将内部事件混入事件流
            events.extend(agent_internal_events)

            work_product = result["work_product"]
            status_report = result["status_report"]
            self._pending_agent_reports[agent_id] = status_report

            # 发射工具调用事件
            for tool_event in result.get("tool_events", []):
                events.append(Event(type="agent.tool_calls_executed", payload=tool_event))

            # 记录 Token 使用（估算）
            tokens_used = self.model_provider.count_tokens(work_product)
            self.watchdog.add_tokens(tokens_used)

            # 归档到 Blackboard
            await self.blackboard_mgr.append_history(
                self.session_id,
                {
                    "type": "agent_work",
                    "round": self.round_num,
                    "agent_id": agent_id,
                    "work_product": work_product,
                    "status_report": {
                        "state": status_report.state,
                        "will": status_report.will.value,
                        "confidence": status_report.confidence,
                        "rationale": status_report.rationale,
                    },
                },
            )

            # 持久化 Agent 上下文（保留记忆，不清空）
            if self.persistence:
                archive = agent_ctx.archive()
                await self.persistence.save_agent_context(
                    agent_id, self.session_id, archive["frames"]
                )

            # 看门狗记录进展
            self.watchdog.record_progress(tokens_used)

            events.append(
                Event(
                    type="system.agent_completed",
                    payload={
                        "round": self.round_num,
                        "agent_id": agent_id,
                        "agent_name": agent.name,
                        "work_product": work_product,
                        "status_report": {
                            "state": status_report.state,
                            "will": status_report.will.value,
                            "confidence": status_report.confidence,
                            "rationale": status_report.rationale,
                        },
                    },
                )
            )

            logger.info(
                "Agent 执行完成",
                session_id=self.session_id,
                agent_id=agent_id,
                state=status_report.state,
                will=status_report.will.value,
            )

        except Exception as e:
            logger.error(
                "Agent 执行失败", session_id=self.session_id, agent_id=agent_id, error=str(e)
            )
            events.append(
                Event(
                    type="system.agent_failed",
                    payload={
                        "round": self.round_num,
                        "agent_id": agent_id,
                        "error": str(e),
                    },
                )
            )
            self.watchdog.record_no_progress()

        return True, events

    async def _execute_parallel(
        self,
        decision: SchedulingDecision,
        current_task: str,
        blackboard_view: dict,
    ) -> Tuple[bool, List[Event]]:
        """执行并行决策：多个 Agent 并发执行任务"""
        events: List[Event] = []
        agent_ids = decision.verification_agents or []
        if not agent_ids and decision.target_agent_id:
            agent_ids = [decision.target_agent_id]

        if not agent_ids:
            return True, events

        logger.info("并行执行", session_id=self.session_id, agent_ids=agent_ids)

        # 构建并发的 assign 任务
        async def run_agent(agent_id: str) -> Tuple[bool, List[Event]]:
            sub_decision = SchedulingDecision(
                decision_type="assign",
                target_agent_id=agent_id,
                task_description=decision.task_description or current_task,
                rationale=decision.rationale,
            )
            return await self._execute_assign(sub_decision, current_task, blackboard_view)

        # 使用 asyncio.gather 并发执行
        results = await asyncio.gather(*[run_agent(aid) for aid in agent_ids])
        for cont, evs in results:
            events.extend(evs)

        return True, events

    def _collect_reports(self) -> List[AgentReport]:
        """收集各 Agent 的状态报告"""
        reports = []
        for agent_id in self.agents:
            if agent_id in self._pending_agent_reports:
                reports.append(self._pending_agent_reports[agent_id])
            else:
                # 默认报告：就绪状态
                reports.append(
                    AgentReport(
                        agent_id=agent_id,
                        state=AgentState.READY,
                        will=AgentWill.EXECUTE,
                        rationale="Agent 就绪",
                    )
                )
        return reports

    def _build_blackboard_view(self, blackboard: dict) -> dict:
        """构建给 Agent 看的 Blackboard 分层视图。

        分层策略：
        - 早期历史由 structured_summaries 替代（避免 Token 膨胀）
        - 近期保留原始记录（保留细节）
        - kv_state 直接注入（结构化状态）
        """
        if not blackboard:
            return {
                "raw_history": [],
                "structured_summaries": [],
                "kv_state": {},
                "version": 0,
            }

        raw_history = blackboard.get("raw_history", [])
        summaries = blackboard.get("structured_summaries", [])

        # 保留最近 10 条原始记录，更早的由 summaries 替代
        recent_history = raw_history[-10:] if len(raw_history) > 10 else raw_history

        return {
            "recent_history": recent_history,
            "structured_summaries": summaries,
            "kv_state": blackboard.get("kv_state", {}),
            "version": blackboard.get("version", 0),
        }

    async def _handle_user_input_to_blackboard(self, content: str):
        """将用户输入记录到 Blackboard"""
        await self.blackboard_mgr.append_history(
            self.session_id,
            {
                "type": "user_input",
                "content": content,
                "round": self.round_num,
            },
        )
        if self.persistence:
            await self.persistence.save_message(
                Message(
                    id=f"msg_{self.session_id}_user_{datetime.utcnow().timestamp()}",
                    conversation_id=self.session_id,
                    agent_id=None,
                    content=content,
                    role="user",
                )
            )

    async def handle_user_input(self, content: str) -> AsyncIterator[Event]:
        """处理用户中途输入。

        如果会话正在运行，输入放入队列等待下一轮调度处理。
        如果会话已完成，重新激活并启动调度循环。
        """
        await self._user_input_queue.put(content)
        yield Event(type="user.input_queued", payload={"content": content})

        if self.status != "running":
            self.status = "running"
            async for event in self._scheduling_loop(content):
                yield event

    def get_status(self) -> dict:
        """获取当前状态"""
        return {
            "session_id": self.session_id,
            "status": self.status,
            "round": self.round_num,
            "agents": [{"id": a.id, "name": a.name, "role": a.role} for a in self.agents.values()],
            "watchdog": self.watchdog.get_status(),
            "user_input_queue": self._user_input_queue.qsize(),
        }
