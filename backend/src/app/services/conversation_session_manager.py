"""Conversation 级会话管理器

管理每个 conversation 的长期运行 AgentSession：
- 创建与复用
- 用户输入发送（支持运行中插队或完成后重启）
- Generation 取消
- Session 关闭与清理

进程内单例。多进程部署时需配合 sticky session 或接受换进程时对话中断。
"""

from __future__ import annotations

import asyncio
from typing import Any, ClassVar, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_runtime import Session as AgentSession
from agent_runtime.core.types import Event as RuntimeEvent
from app.events import WebSocketSink
from db.models import Conversation, Message, utcnow
from db.session import AsyncSessionLocal
from app.services.runtime.generation_records import (
    create_generation_record,
    finish_generation_record,
    record_generation_event,
)
from app.services.serialization import message_to_dict
from app.services.chat.scheduling import resolve_scheduling_strategy, runtime_mode, workflow_enabled
from app.services.runtime_service import OrchestratorService
from common.logger import get_logger

logger = get_logger("app.services.conversation_session_manager")


class SessionNotFoundError(Exception):
    """Session 不存在"""

    pass


class SessionAlreadyRunningError(Exception):
    """Generation 已在运行中"""

    pass


class ConversationSessionManager:
    """Conversation 级会话管理器（进程内单例）。"""

    _instance: ClassVar[Optional["ConversationSessionManager"]] = None

    def __init__(self, session_factory: Any = None):
        self._sessions: dict[str, AgentSession] = {}
        self._session_model_config_ids: dict[str, str | None] = {}
        self._session_scheduling_strategies: dict[str, str] = {}
        self._session_runtime_modes: dict[str, str] = {}
        self._session_workflow_enabled: dict[str, bool] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._running_tasks: dict[str, asyncio.Task] = {}
        self._generation_ids: dict[str, str] = {}
        self._pending_preview_message_ids: dict[str, list[str]] = {}
        self._session_factory = session_factory or AsyncSessionLocal

    @classmethod
    def get_instance(cls) -> "ConversationSessionManager":
        """获取单例实例。"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _get_lock(self, conversation_id: str) -> asyncio.Lock:
        """获取 conversation 级别的并发锁。"""
        if conversation_id not in self._locks:
            self._locks[conversation_id] = asyncio.Lock()
        return self._locks[conversation_id]

    async def get_or_create_session(
        self,
        db: AsyncSession,
        conversation: Conversation,
        model_config_id: str | None = None,
        event_sink=None,
    ) -> AgentSession:
        """获取或创建 conversation 的 Session。

        如果 Session 已存在，直接返回。否则创建新 Session 并缓存。
        """
        conversation_id = str(conversation.id)
        requested_model_config_id = str(model_config_id) if model_config_id else None
        requested_strategy = resolve_scheduling_strategy(conversation)
        requested_runtime_mode = runtime_mode(conversation)
        requested_workflow_enabled = workflow_enabled(conversation)

        async with self._get_lock(conversation_id):
            if conversation_id in self._sessions:
                task = self._running_tasks.get(conversation_id)
                if task and not task.done():
                    return self._sessions[conversation_id]
                if (
                    self._session_model_config_ids.get(conversation_id) == requested_model_config_id
                    and self._session_scheduling_strategies.get(conversation_id) == requested_strategy
                    and self._session_runtime_modes.get(conversation_id) == requested_runtime_mode
                    and self._session_workflow_enabled.get(conversation_id) == requested_workflow_enabled
                ):
                    if event_sink is not None:
                        self._sessions[conversation_id].event_dispatcher.register_sink(event_sink)
                    return self._sessions[conversation_id]
                self._sessions.pop(conversation_id, None)
                self._session_model_config_ids.pop(conversation_id, None)
                self._session_scheduling_strategies.pop(conversation_id, None)
                self._session_runtime_modes.pop(conversation_id, None)
                self._session_workflow_enabled.pop(conversation_id, None)

            agents = await OrchestratorService._get_conversation_agents(db, conversation)
            if not agents:
                raise ValueError(f"会话没有可用 Agent conversation_id={conversation_id}")

            session = await OrchestratorService.create_session(
                db,
                conversation,
                agents,
                model_config_id,
                event_sink=event_sink,
                scheduling_strategy=requested_strategy,
            )
            self._sessions[conversation_id] = session
            self._session_model_config_ids[conversation_id] = requested_model_config_id
            self._session_scheduling_strategies[conversation_id] = requested_strategy
            self._session_runtime_modes[conversation_id] = requested_runtime_mode
            self._session_workflow_enabled[conversation_id] = requested_workflow_enabled

            # 更新数据库状态
            conversation.generation_status = "idle"
            conversation.active_session_id = session.session_id
            await db.commit()

            logger.info(
                "Session 创建",
                conversation_id=conversation_id,
                session_id=session.session_id,
                agent_count=len(agents),
            )
            return session

    async def start_generation(
        self,
        conversation_id: str,
        content: str,
    ) -> None:
        """启动 generation。

        首次发送消息或 Session 完成后重新启动时调用。
        如果已有运行中的 generation，抛出 SessionAlreadyRunningError。
        """
        session = self._sessions.get(conversation_id)
        if not session:
            raise SessionNotFoundError(f"Conversation {conversation_id} 没有活跃 Session")

        if conversation_id in self._running_tasks:
            task = self._running_tasks[conversation_id]
            if not task.done():
                raise SessionAlreadyRunningError(f"Conversation {conversation_id} 已有运行中的 generation")

        generation_id = await self._create_generation_record(conversation_id, session, content)
        task = asyncio.create_task(
            self._run_generation(session, conversation_id, generation_id, content),
            name=f"generation-{conversation_id}",
        )
        self._running_tasks[conversation_id] = task
        task.add_done_callback(
            lambda t, cid=conversation_id, gid=generation_id: self._on_generation_done(cid, gid, t)
        )

        logger.info("Generation 启动", conversation_id=conversation_id, content_preview=content[:50])

    async def _run_generation(
        self,
        session: AgentSession,
        conversation_id: str,
        generation_id: str,
        content: str,
    ) -> None:
        """在后台运行 Session generation。

        事件已通过 EventDispatcher 分发到各 Sink，这里只需消费迭代器。
        """
        async for event in session.run(content):
            await self._record_generation_event(conversation_id, generation_id, event)

    async def send_user_input(
        self,
        conversation_id: str,
        content: str,
    ) -> None:
        """向 Session 发送用户输入。

        如果 Session 正在运行，输入放入队列等待处理（插队）。
        如果 Session 已完成，重新启动 generation。
        """
        session = self._sessions.get(conversation_id)
        if not session:
            raise SessionNotFoundError(f"Conversation {conversation_id} 没有活跃 Session")

        status_info = session.get_status()
        status = status_info.get("status") or ("running" if status_info.get("running") else "idle")

        if status == "running":
            # 运行中：通过 send_message 插队
            logger.info("用户输入插队", conversation_id=conversation_id, content_preview=content[:50])
            generation_id = self._generation_ids.get(conversation_id)
            async for event in session.send_message(content):
                if generation_id:
                    await self._record_generation_event(conversation_id, generation_id, event)
        else:
            # 已完成：重新启动 generation
            logger.info("用户输入重启 generation", conversation_id=conversation_id, content_preview=content[:50])
            task = self._running_tasks.get(conversation_id)
            if task and not task.done():
                try:
                    await asyncio.wait_for(asyncio.shield(task), timeout=2.0)
                except asyncio.TimeoutError as exc:
                    raise SessionAlreadyRunningError(
                        f"Conversation {conversation_id} is still finishing the previous generation"
                    ) from exc
            await self.start_generation(conversation_id, content)

    async def cancel_generation(self, conversation_id: str) -> bool:
        """取消当前 generation。

        取消运行中的 asyncio.Task，通过 WebSocketSink 推送 control.cancel 事件。
        """
        task = self._running_tasks.get(conversation_id)
        if task and not task.done():
            session = self._sessions.get(conversation_id)
            cancel = getattr(session, "cancel", None) if session else None
            if cancel:
                await cancel("user_cancelled")
            task.cancel()
            logger.info("Generation 取消", conversation_id=conversation_id)

            # 通过 WebSocketSink 推送 control.cancel 事件
            cancel_event = RuntimeEvent(
                type="control.cancel",
                payload={"conversation_id": conversation_id, "reason": "user_cancelled"},
            )
            ws_sink = WebSocketSink(conversation_id)
            await ws_sink.emit(cancel_event)
            generation_id = self._generation_ids.pop(conversation_id, None)
            if generation_id:
                self._pending_preview_message_ids.pop(generation_id, None)
                await self._record_generation_event(conversation_id, generation_id, cancel_event)
                await self._finish_generation(
                    conversation_id,
                    generation_id,
                    status="cancelled",
                    error="user_cancelled",
                )

            return True
        return False

    def _on_generation_done(self, conversation_id: str, generation_id: str, task: asyncio.Task) -> None:
        """Generation 任务完成回调。"""
        self._running_tasks.pop(conversation_id, None)

        try:
            task.result()
            logger.info("Generation 完成", conversation_id=conversation_id)
            status = "completed"
            error = None
        except asyncio.CancelledError:
            logger.info("Generation 被取消", conversation_id=conversation_id)
            status = "cancelled"
            error = "cancelled"
        except Exception as e:
            logger.error("Generation 异常", conversation_id=conversation_id, error=str(e))
            status = "failed"
            error = str(e)

        if self._generation_ids.get(conversation_id) != generation_id:
            return
        self._generation_ids.pop(conversation_id, None)
        try:
            asyncio.create_task(
                self._finish_generation(conversation_id, generation_id, status=status, error=error)
            )
        except RuntimeError:
            logger.warning("Generation 终态持久化任务创建失败", conversation_id=conversation_id)

    async def close_session(self, conversation_id: str) -> None:
        """关闭并清理 Session。

        取消运行中的 generation，从内存中移除 Session。
        """
        await self.cancel_generation(conversation_id)
        session = self._sessions.pop(conversation_id, None)
        self._session_model_config_ids.pop(conversation_id, None)
        self._session_scheduling_strategies.pop(conversation_id, None)
        self._session_runtime_modes.pop(conversation_id, None)
        self._session_workflow_enabled.pop(conversation_id, None)
        generation_id = self._generation_ids.pop(conversation_id, None)
        if generation_id:
            self._pending_preview_message_ids.pop(generation_id, None)
        self._locks.pop(conversation_id, None)

        if session:
            logger.info("Session 关闭", conversation_id=conversation_id, session_id=session.session_id)

    def get_session_status(self, conversation_id: str) -> dict | None:
        """获取 Session 状态。"""
        session = self._sessions.get(conversation_id)
        if not session:
            return None
        return session.get_status()

    def is_generation_running(self, conversation_id: str) -> bool:
        """检查是否有运行中的 generation。"""
        task = self._running_tasks.get(conversation_id)
        return task is not None and not task.done()

    async def _create_generation_record(
        self,
        conversation_id: str,
        session: AgentSession,
        content: str,
    ) -> str:
        async with self._session_factory() as db:
            generation_id = await create_generation_record(
                db,
                conversation_id,
                session_id=session.session_id,
                agents=session.agents.values(),
                prompt=content,
                model_config_id=self._session_model_config_ids.get(conversation_id),
                scheduling_strategy=self._session_scheduling_strategies.get(conversation_id),
                runtime_mode=self._session_runtime_modes.get(conversation_id),
                workflow_enabled=self._session_workflow_enabled.get(conversation_id),
            )
        self._generation_ids[conversation_id] = generation_id
        return generation_id

    async def _record_generation_event(
        self,
        conversation_id: str,
        generation_id: str,
        event: RuntimeEvent,
    ) -> None:
        self._collect_preview_message_id(generation_id, event)
        async with self._session_factory() as db:
            await record_generation_event(db, conversation_id, generation_id, event)
            message = await self._persist_agent_report_message(
                db,
                conversation_id,
                generation_id,
                event,
            )
        if message:
            sink = WebSocketSink(conversation_id)
            await sink.emit(RuntimeEvent(type="message:new", payload=message_to_dict(message)))
            await self._publish_pending_preview_messages(sink, conversation_id, generation_id)

    def _collect_preview_message_id(self, generation_id: str, event: RuntimeEvent) -> None:
        if event.type != "agent.tool_result":
            return
        payload = event.payload or {}
        result = payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(result, dict):
            return
        output = result.get("output") if isinstance(result.get("output"), dict) else result
        if not isinstance(output, dict):
            return
        preview_id = str(output.get("preview_message_id") or "")
        if not preview_id:
            return
        pending = self._pending_preview_message_ids.setdefault(generation_id, [])
        if preview_id not in pending:
            pending.append(preview_id)

    async def _publish_pending_preview_messages(
        self,
        sink: WebSocketSink,
        conversation_id: str,
        generation_id: str,
    ) -> None:
        preview_ids = self._pending_preview_message_ids.pop(generation_id, [])
        if not preview_ids:
            return
        async with self._session_factory() as db:
            for preview_id in preview_ids:
                preview = await db.get(Message, preview_id)
                if (
                    not preview
                    or str(preview.conversation_id) != conversation_id
                    or preview.content_type != "preview_card"
                    or preview.deleted_at is not None
                ):
                    continue
                preview.created_at = utcnow()
                preview.updated_at = utcnow()
                await db.commit()
                await db.refresh(preview)
                await sink.emit(RuntimeEvent(type="message:new", payload=message_to_dict(preview)))

    async def _persist_agent_report_message(
        self,
        db: AsyncSession,
        conversation_id: str,
        generation_id: str,
        event: RuntimeEvent,
    ) -> Message | None:
        if event.type not in {"agent.report", "system.agent_completed"}:
            return None
        payload = event.payload or {}
        work_product = str(payload.get("work_product") or "").strip()
        if not work_product:
            return None

        agent_id = str(payload.get("agent_id") or "")
        session = self._sessions.get(conversation_id)
        agent = session.agents.get(agent_id) if session and agent_id else None
        agent_name = getattr(agent, "name", None) or str(payload.get("agent_name") or "Agent")
        if event.type == "system.agent_completed":
            persisted = await db.scalar(
                select(Message)
                .where(
                    Message.conversation_id == conversation_id,
                    Message.sender_type == "agent",
                    Message.sender_id == agent_id,
                    Message.content["text"].as_string() == work_product,
                    Message.deleted_at.is_(None),
                )
                .order_by(Message.created_at.desc())
            )
            if persisted:
                conversation = await db.get(Conversation, conversation_id)
                if conversation:
                    conversation.last_message_preview = work_product[:300]
                    conversation.last_message_sender = persisted.sender_name or agent_name
                    conversation.last_message_at = utcnow()
                await db.commit()
                await db.refresh(persisted)
                return persisted
        existing = await db.scalar(
            select(Message).where(
                Message.conversation_id == conversation_id,
                Message.sender_type == "agent",
                Message.sender_id == agent_id,
                Message.extra["runtime_generation_id"].as_string() == generation_id,
                Message.extra["runtime_report_task"].as_string() == str(payload.get("task") or ""),
                Message.deleted_at.is_(None),
            )
        )
        if existing:
            return None

        report = payload.get("report") if isinstance(payload.get("report"), dict) else {}
        message = Message(
            conversation_id=conversation_id,
            sender_type="agent",
            sender_id=agent_id or None,
            sender_name=agent_name,
            content_type="text",
            content={
                "text": work_product,
                "runtime_report": report,
            },
            status="completed",
            extra={
                "runtime_generation_id": generation_id,
                "runtime_agent_report": True,
                "runtime_report_task": str(payload.get("task") or ""),
            },
        )
        conversation = await db.get(Conversation, conversation_id)
        if conversation:
            conversation.last_message_preview = work_product[:300]
            conversation.last_message_sender = agent_name
            conversation.last_message_at = utcnow()
            conversation.message_count += 1
        db.add(message)
        await db.commit()
        await db.refresh(message)
        return message

    async def _finish_generation(
        self,
        conversation_id: str,
        generation_id: str,
        *,
        status: str,
        error: str | None = None,
    ) -> None:
        async with self._session_factory() as db:
            await finish_generation_record(
                db,
                conversation_id,
                generation_id,
                status=status,
                error=error,
            )
        event_type = {
            "cancelled": "generation:cancelled",
            "failed": "generation:failed",
        }.get(status, "generation_finished")
        await WebSocketSink(conversation_id).emit(
            RuntimeEvent(
                type=event_type,
                payload={
                    "conversation_id": conversation_id,
                    "generation_id": generation_id,
                    "status": status,
                    "error": error,
                },
            )
        )
