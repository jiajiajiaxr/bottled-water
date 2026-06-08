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
from typing import Any, Dict, List, Optional, AsyncIterator, Tuple

from model_provider.core.interfaces import BaseModelProvider

from common.logger import get_logger
from ..core.types import (
    AgentConfig,
    AgentReport,
    AgentState,
    AgentWill,
    Event,
    SchedulingDecision,
)
from ..core.interfaces import AgentContextProvider, PersistenceBackend, ToolExecutor
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
        context_provider: Optional[AgentContextProvider] = None,
    ):
        self.session_id = session_id
        self.agents = agents
        self.scheduler = scheduler
        self.model_provider = model_provider
        self.persistence = persistence
        self.tool_executor = tool_executor
        self.context_provider = context_provider
        self.watchdog = Watchdog(watchdog_config)

        # 上下文管理
        self.blackboard_mgr = BlackboardManager(persistence=persistence)
        self.agent_ctx_mgr = AgentContextManager()

        # 状态
        self.status = "idle"  # idle | running | paused | completed | failed
        self.round_num = 0
        self._user_input_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._agent_loops: Dict[str, AgentLoop] = {}
        self._pending_agent_reports: Dict[str, AgentReport] = {}
        self._persistence_lock = asyncio.Lock()
        self._current_context_metadata: dict[str, Any] = {}
        self._mention_target_ids: list[str] = []
        self._mention_dispatched_ids: set[str] = set()

    async def run(
        self,
        user_message: str,
        context_metadata: Optional[dict[str, Any]] = None,
    ) -> AsyncIterator[Event]:
        """运行会话调度循环"""
        self.status = "running"
        logger.info("调度循环开始", session_id=self.session_id, agents=list(self.agents.keys()))

        # 1. 初始化
        await self._initialize(user_message, context_metadata=context_metadata)

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

    async def _initialize(
        self,
        user_message: str,
        context_metadata: Optional[dict[str, Any]] = None,
    ):
        """初始化 Blackboard 和 Agent 上下文"""
        # 重置调度器与看门狗状态（支持 Session 复用场景）
        self.scheduler.reset()
        self.watchdog.reset()

        # 重置本地状态
        self.round_num = 0
        self._pending_agent_reports.clear()
        self._agent_loops.clear()
        self._user_input_queue = asyncio.Queue()
        self._current_context_metadata = self._normalize_context_metadata(
            user_message,
            context_metadata,
        )
        self._reset_mention_scope(user_message, self._current_context_metadata)

        # 加载已有 Blackboard，不存在则创建
        blackboard = await self.blackboard_mgr.get(self.session_id)
        if not blackboard:
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

        # 加载历史消息注入 AgentContext
        if self.persistence:
            try:
                history = await self.persistence.load_messages(self.session_id, limit=50)
                for agent_id, agent in self.agents.items():
                    ctx = self.agent_ctx_mgr.get(agent_id, self.session_id)
                    ctx.system_prompt = agent.system_prompt
                    ctx.role_config = {"name": agent.name, "role": agent.role, "tools": agent.tools}
                    for msg in reversed(history):
                        if msg.role == "user":
                            ctx.add("thought", f"【用户】{msg.content}")
                        elif msg.role == "assistant" and msg.agent_id == agent_id:
                            ctx.add("thought", msg.content)
                        elif msg.role == "assistant":
                            ctx.add("thought", f"【{msg.agent_id or '其他 Agent'}】{msg.content}")
            except Exception:
                logger.warning("加载历史消息失败", session_id=self.session_id, exc_info=True)

        # 初始化各 Agent Loop
        for agent_id, agent in self.agents.items():
            if agent_id not in self._agent_loops:
                self._agent_loops[agent_id] = AgentLoop(
                    agent_config=agent,
                    model_provider=self.model_provider,
                    use_streaming=True,
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
                content = str(user_input.get("content") or "")
                self._current_context_metadata = self._normalize_context_metadata(
                    content,
                    user_input.get("context_metadata"),
                )
                self._reset_mention_scope(content, self._current_context_metadata)
                await self._handle_user_input_to_blackboard(content)
                current_task = content  # 用户输入成为新任务
                yield Event(type="user.input_received", payload={"content": content})
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
                await self._archive_watchdog_event(watchdog_event)
                yield Event(type="control.watchdog_triggered", payload=watchdog_event.payload)
                self.status = "completed"
                return

            # --- 4. 调度器决策 ---
            decision = self._mention_decision(reports, current_task)
            if decision is None:
                decision = await self.scheduler.make_decision(
                    blackboard=blackboard_view,
                    agent_reports=reports,
                    conversation_context={
                        "session_id": self.session_id,
                        "round": self.round_num,
                        "current_task": current_task,
                        "agent_count": len(reports),
                    },
                )
            decision = self._scope_decision_to_mentions(decision, reports, current_task)
            logger.info(
                "调度决策",
                session_id=self.session_id,
                round=self.round_num,
                decision=decision.decision_type,
                target=decision.target_agent_id,
            )
            await self._append_blackboard_history(
                {
                    "type": "scheduling_decision",
                    "round": self.round_num,
                    "decision": {
                        "decision_type": decision.decision_type,
                        "target_agent_id": decision.target_agent_id,
                        "task_description": decision.task_description,
                        "rationale": decision.rationale,
                        "requires_verification": decision.requires_verification,
                        "verification_agents": decision.verification_agents,
                    },
                }
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
                await self._archive_watchdog_event(watchdog_event)
                yield Event(type="control.watchdog_triggered", payload=watchdog_event.payload)
                self.status = "completed"
                return

            # --- 6. 执行决策 ---
            execution_state = {"should_continue": True}
            async for event in self._execute_decision_stream(
                decision, current_task, blackboard_view, execution_state
            ):
                yield event
            if not execution_state["should_continue"]:
                break

            # --- 7. 判断循环是否继续 ---
            all_completed = all(r.will.value == "complete" for r in reports)
            if all_completed and len(reports) == len(self._active_agent_ids()):
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

    async def _execute_decision_stream(
        self,
        decision: SchedulingDecision,
        current_task: str,
        blackboard_view: dict,
        execution_state: dict[str, bool],
    ) -> AsyncIterator[Event]:
        if decision.decision_type == "assign":
            async for event in self._execute_assign_stream(
                decision, current_task, blackboard_view, execution_state
            ):
                yield event
            return

        should_continue, events = await self._execute_decision(
            decision, current_task, blackboard_view
        )
        execution_state["should_continue"] = should_continue
        for event in events:
            yield event

    async def _execute_assign_stream(
        self,
        decision: SchedulingDecision,
        current_task: str,
        blackboard_view: dict,
        execution_state: dict[str, bool],
    ) -> AsyncIterator[Event]:
        """Execute a single-agent assignment while yielding runtime events live."""
        target_ids = self._decision_target_ids(decision.target_agent_id)
        if len(target_ids) > 1:
            decision.target_agent_ids = target_ids
            decision.decision_type = "parallel"
            should_continue, events = await self._execute_parallel(
                decision, current_task, blackboard_view
            )
            execution_state["should_continue"] = should_continue
            for event in events:
                yield event
            return

        agent_id = target_ids[0] if target_ids else None
        if not agent_id or agent_id not in self.agents:
            logger.error("指派目标无效", session_id=self.session_id, target=agent_id)
            execution_state["should_continue"] = True
            return

        if agent_id in self._mention_target_ids:
            self._mention_dispatched_ids.add(agent_id)

        agent = self.agents[agent_id]
        agent_loop = self._agent_loops[agent_id]
        task = decision.task_description or current_task

        logger.info("Agent 执行开始", session_id=self.session_id, agent_id=agent_id, task=task[:50])

        agent_ctx = self.agent_ctx_mgr.get(agent_id, self.session_id)
        agent_ctx.add("task", task)
        agent_ctx.current_round = self.round_num
        agent_ctx.current_task = task

        yield Event(
            type="system.agent_started",
            payload={
                "round": self.round_num,
                "agent_id": agent_id,
                "agent_name": agent.name,
                "task": task,
            },
        )

        try:
            internal_events: asyncio.Queue[Event] = asyncio.Queue()

            async def _emit_agent_event(event: Event):
                await internal_events.put(event)

            agent_task = asyncio.create_task(
                agent_loop.run(
                    task=task,
                    blackboard_view=blackboard_view,
                    tool_executor=self.tool_executor,
                    agent_ctx=agent_ctx,
                    emit_event=_emit_agent_event,
                    context_provider=self.context_provider,
                    context_metadata=self._current_context_metadata,
                ),
                name=f"orchestrator-agent:{agent_id}",
            )

            while not agent_task.done():
                try:
                    event = await asyncio.wait_for(internal_events.get(), timeout=0.05)
                except asyncio.TimeoutError:
                    continue
                yield event

            while not internal_events.empty():
                yield internal_events.get_nowait()

            result = agent_task.result()

            work_product = result["work_product"]
            status_report = result["status_report"]
            self._pending_agent_reports[agent_id] = status_report

            for tool_event in result.get("tool_events", []):
                yield Event(type="agent.tool_calls_executed", payload=tool_event)

            tokens_used = self.model_provider.count_tokens(work_product)
            self.watchdog.add_tokens(tokens_used)

            await self._append_blackboard_history(
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
                }
            )

            if self.persistence:
                archive = agent_ctx.archive()
                async with self._persistence_lock:
                    await self.persistence.save_agent_context(
                        agent_id, self.session_id, archive["frames"]
                    )

            self.watchdog.record_progress(tokens_used)

            yield Event(
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

            logger.info(
                "Agent 执行完成",
                session_id=self.session_id,
                agent_id=agent_id,
                state=status_report.state,
                will=status_report.will.value,
            )
        except Exception as e:
            logger.error("Agent 执行失败", session_id=self.session_id, agent_id=agent_id, error=str(e))
            self._pending_agent_reports[agent_id] = AgentReport(
                agent_id=agent_id,
                state=AgentState.FAILED,
                will=AgentWill.BLOCKED,
                blockers=[str(e)],
                confidence=0.0,
                rationale=f"Agent execution failed: {type(e).__name__}",
            )
            await self._append_blackboard_history(
                {
                    "type": "agent_error",
                    "round": self.round_num,
                    "agent_id": agent_id,
                    "task": task,
                    "error": str(e),
                    "error_type": type(e).__name__,
                }
            )
            yield Event(
                type="system.agent_failed",
                payload={
                    "round": self.round_num,
                    "agent_id": agent_id,
                    "error": str(e),
                },
            )
            self.watchdog.record_no_progress()

        execution_state["should_continue"] = True

    async def _execute_assign(
        self,
        decision: SchedulingDecision,
        current_task: str,
        blackboard_view: dict,
    ) -> Tuple[bool, List[Event]]:
        """执行指派决策：让目标 Agent 执行任务"""
        events: List[Event] = []
        target_ids = self._decision_target_ids(decision.target_agent_id)
        if len(target_ids) > 1:
            decision.target_agent_ids = target_ids
            decision.decision_type = "parallel"
            return await self._execute_parallel(decision, current_task, blackboard_view)
        agent_id = target_ids[0] if target_ids else None
        if not agent_id or agent_id not in self.agents:
            logger.error("指派目标无效", session_id=self.session_id, target=agent_id)
            return True, events

        if agent_id in self._mention_target_ids:
            self._mention_dispatched_ids.add(agent_id)

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
                context_provider=self.context_provider,
                context_metadata=self._current_context_metadata,
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
            await self._append_blackboard_history(
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
                }
            )

            # 持久化助手消息到数据库
            # Assistant chat messages are persisted by ConversationSessionManager
            # from system.agent_completed. Do not write them here as well.

            # 持久化 Agent 上下文（保留记忆，不清空）
            if self.persistence:
                archive = agent_ctx.archive()
                async with self._persistence_lock:
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
            self._pending_agent_reports[agent_id] = AgentReport(
                agent_id=agent_id,
                state=AgentState.FAILED,
                will=AgentWill.BLOCKED,
                blockers=[str(e)],
                confidence=0.0,
                rationale=f"Agent execution failed: {type(e).__name__}",
            )
            await self._append_blackboard_history(
                {
                    "type": "agent_error",
                    "round": self.round_num,
                    "agent_id": agent_id,
                    "task": task,
                    "error": str(e),
                    "error_type": type(e).__name__,
                }
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
        agent_ids = self._decision_target_ids(
            decision.target_agent_ids,
            decision.verification_agents,
            decision.target_agent_id,
        )

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
        results = await asyncio.gather(*[run_agent(aid) for aid in agent_ids], return_exceptions=True)
        for agent_id, result in zip(agent_ids, results):
            if isinstance(result, Exception):
                logger.error(
                    "Parallel agent branch failed outside assign handler",
                    session_id=self.session_id,
                    agent_id=agent_id,
                    error=str(result),
                )
                self._pending_agent_reports[agent_id] = AgentReport(
                    agent_id=agent_id,
                    state=AgentState.FAILED,
                    will=AgentWill.BLOCKED,
                    blockers=[str(result)],
                    confidence=0.0,
                    rationale=f"Parallel branch failed: {type(result).__name__}",
                )
                await self._append_blackboard_history(
                    {
                        "type": "agent_error",
                        "round": self.round_num,
                        "agent_id": agent_id,
                        "task": decision.task_description or current_task,
                        "error": str(result),
                        "error_type": type(result).__name__,
                    }
                )
                events.append(
                    Event(
                        type="system.agent_failed",
                        payload={
                            "round": self.round_num,
                            "agent_id": agent_id,
                            "error": str(result),
                        },
                    )
                )
                continue
            _cont, evs = result
            events.extend(self._compact_parallel_events(evs))

        return True, events

    def _decision_target_ids(self, *values: Any) -> list[str]:
        """Flatten scheduler target fields into valid unique Agent IDs."""
        flattened: list[str] = []

        def collect(value: Any) -> None:
            if value is None:
                return
            if isinstance(value, (list, tuple, set)):
                for item in value:
                    collect(item)
                return
            agent_id = str(value)
            if agent_id in self.agents:
                flattened.append(agent_id)

        for value in values:
            collect(value)
        targets = list(dict.fromkeys(flattened))
        if self._mention_target_ids:
            allowed = set(self._mention_target_ids)
            targets = [agent_id for agent_id in targets if agent_id in allowed]
        return targets

    def _compact_parallel_events(self, events: list[Event]) -> list[Event]:
        """Keep structural events when replaying finished parallel branches.

        The legacy parallel executor gathers branch events and replays them after
        all branches finish. Replaying every token delta at that point is no longer
        real streaming and can block generation finalization for large outputs.
        """
        noisy_types = {"agent.token", "agent.delta", "content_block_delta"}
        return [event for event in events if event.type not in noisy_types]

    def _collect_reports(self) -> List[AgentReport]:
        """收集各 Agent 的状态报告"""
        reports = []
        for agent_id in self._active_agent_ids():
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

    def _reset_mention_scope(self, content: str, context_metadata: dict[str, Any]) -> None:
        self._mention_target_ids = self._resolve_mention_target_ids(content, context_metadata)
        self._mention_dispatched_ids.clear()

    def _resolve_mention_target_ids(
        self,
        content: str,
        context_metadata: dict[str, Any] | None,
    ) -> list[str]:
        metadata = context_metadata or {}
        targets: list[str] = []

        def add(agent_id: Any) -> None:
            normalized = str(agent_id or "").strip()
            if normalized in self.agents and normalized not in targets:
                targets.append(normalized)

        raw_targets = metadata.get("mention_target_agent_ids")
        if isinstance(raw_targets, (list, tuple, set)):
            for item in raw_targets:
                add(item)

        raw_mentions = metadata.get("agent_mentions")
        if isinstance(raw_mentions, list):
            for item in raw_mentions:
                if isinstance(item, dict):
                    add(item.get("agent_id") or item.get("id"))

        if targets:
            return targets

        lowered = (content or "").lower()
        if not lowered:
            return []
        for agent_id, config in self.agents.items():
            candidates = {
                f"agent_id={agent_id.lower()}",
                f"@{agent_id.lower()}",
            }
            name = (config.name or "").strip().lower()
            if name:
                candidates.add(f"@{name}")
            if any(candidate in lowered for candidate in candidates):
                add(agent_id)
        return targets

    def _active_agent_ids(self) -> list[str]:
        if self._mention_target_ids:
            return [agent_id for agent_id in self._mention_target_ids if agent_id in self.agents]
        return list(self.agents)

    def _mention_decision(
        self,
        reports: list[AgentReport],
        current_task: str,
    ) -> SchedulingDecision | None:
        targets = self._active_agent_ids() if self._mention_target_ids else []
        if not targets:
            return None
        report_by_agent = {report.agent_id: report for report in reports}

        def is_terminal(agent_id: str) -> bool:
            report = report_by_agent.get(agent_id)
            return bool(report and report.state in {AgentState.COMPLETED, AgentState.FAILED})

        pending = [
            agent_id
            for agent_id in targets
            if agent_id not in self._mention_dispatched_ids and not is_terminal(agent_id)
        ]
        if pending:
            return SchedulingDecision(
                decision_type="parallel" if len(pending) > 1 else "assign",
                action="assign",
                target_agent_id=pending[0],
                target_agent_ids=pending,
                task=current_task,
                task_description=current_task,
                rationale="Explicit user mention restricts this turn to the mentioned Agent(s).",
                expected_outputs=["Direct response from the mentioned Agent(s)."],
            )

        unfinished = [agent_id for agent_id in targets if not is_terminal(agent_id)]
        if unfinished:
            return SchedulingDecision(
                decision_type="wait",
                action="wait",
                target_agent_id=unfinished[0],
                target_agent_ids=unfinished,
                task=current_task,
                task_description=current_task,
                rationale="Mentioned Agent has already been assigned; waiting for its terminal report.",
            )

        return SchedulingDecision(
            decision_type="complete",
            action="complete",
            target_agent_id=targets[0],
            target_agent_ids=targets,
            task=current_task,
            task_description=current_task,
            rationale="Mentioned Agent reached a terminal report; ending this turn.",
        )

    def _scope_decision_to_mentions(
        self,
        decision: SchedulingDecision,
        reports: list[AgentReport],
        current_task: str,
    ) -> SchedulingDecision:
        targets = self._active_agent_ids() if self._mention_target_ids else []
        if not targets:
            return decision

        if decision.decision_type in {"assign", "parallel"}:
            scoped_targets = self._decision_target_ids(
                decision.target_agent_ids,
                decision.verification_agents,
                decision.target_agent_id,
            )
            if not scoped_targets:
                scoped_targets = [
                    agent_id
                    for agent_id in targets
                    if agent_id not in self._mention_dispatched_ids
                ] or targets
            decision.decision_type = "parallel" if len(scoped_targets) > 1 else "assign"
            decision.action = "assign"
            decision.target_agent_id = scoped_targets[0]
            decision.target_agent_ids = scoped_targets
            return decision

        if decision.decision_type == "complete":
            report_by_agent = {report.agent_id: report for report in reports}
            unfinished = [
                agent_id
                for agent_id in targets
                if not (
                    report_by_agent.get(agent_id)
                    and report_by_agent[agent_id].state in {AgentState.COMPLETED, AgentState.FAILED}
                )
            ]
            if unfinished:
                return self._mention_decision(reports, current_task) or decision
            decision.target_agent_id = decision.target_agent_id or targets[0]
            decision.target_agent_ids = targets
            return decision

        if decision.decision_type == "wait":
            decision.target_agent_id = decision.target_agent_id or targets[0]
            decision.target_agent_ids = targets
            return decision

        return self._mention_decision(reports, current_task) or decision

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

    async def _archive_watchdog_event(self, event: Event) -> None:
        await self._append_blackboard_history(
            {
                "type": "watchdog_triggered",
                "round": self.round_num,
                "payload": event.payload,
            }
        )

    async def _append_blackboard_history(self, entry: dict) -> None:
        try:
            async with self._persistence_lock:
                await self.blackboard_mgr.append_history(self.session_id, entry)
        except Exception:
            logger.warning(
                "Blackboard runtime history archive failed",
                session_id=self.session_id,
                entry_type=entry.get("type"),
                exc_info=True,
            )

    async def handle_user_input(
        self,
        content: str,
        context_metadata: Optional[dict[str, Any]] = None,
    ) -> AsyncIterator[Event]:
        """处理用户中途输入。

        如果会话正在运行，输入放入队列等待下一轮调度处理。
        如果会话已完成，重新激活并启动调度循环。
        """
        await self._user_input_queue.put(
            {
                "content": content,
                "context_metadata": self._normalize_context_metadata(content, context_metadata),
            }
        )
        yield Event(type="user.input_queued", payload={"content": content})

        if self.status != "running":
            self.status = "running"
            async for event in self._scheduling_loop(content):
                yield event

    def _normalize_context_metadata(
        self,
        content: str,
        metadata: Optional[dict[str, Any]],
    ) -> dict[str, Any]:
        normalized = dict(metadata or {})
        normalized.setdefault("conversation_id", self.session_id)
        normalized.setdefault("session_id", self.session_id)
        if content:
            normalized.setdefault("visible_content", content)
        return normalized

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
