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
from typing import ClassVar, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from agent_runtime import Session as AgentSession
from agent_runtime.core.types import Event as RuntimeEvent
from app.events import WebSocketSink
from db.models import Conversation
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

    def __init__(self):
        self._sessions: dict[str, AgentSession] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._running_tasks: dict[str, asyncio.Task] = {}

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

        async with self._get_lock(conversation_id):
            if conversation_id in self._sessions:
                return self._sessions[conversation_id]

            agents = await OrchestratorService._get_conversation_agents(db, conversation)
            if not agents:
                raise ValueError(f"会话没有可用 Agent conversation_id={conversation_id}")

            session = await OrchestratorService.create_session(
                db,
                conversation,
                agents,
                model_config_id,
                event_sink=event_sink,
            )
            self._sessions[conversation_id] = session

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

        task = asyncio.create_task(
            self._run_generation(session, content),
            name=f"generation-{conversation_id}",
        )
        self._running_tasks[conversation_id] = task
        task.add_done_callback(
            lambda t, cid=conversation_id: self._on_generation_done(cid, t)
        )

        logger.info("Generation 启动", conversation_id=conversation_id, content_preview=content[:50])

    async def _run_generation(self, session: AgentSession, content: str) -> None:
        """在后台运行 Session generation。

        事件已通过 EventDispatcher 分发到各 Sink，这里只需消费迭代器。
        """
        async for _event in session.run(content):
            pass

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

        status = session.get_status()["status"]

        if status == "running":
            # 运行中：通过 send_message 插队
            logger.info("用户输入插队", conversation_id=conversation_id, content_preview=content[:50])
            async for _event in session.send_message(content):
                pass
        else:
            # 已完成：重新启动 generation
            logger.info("用户输入重启 generation", conversation_id=conversation_id, content_preview=content[:50])
            await self.start_generation(conversation_id, content)

    async def cancel_generation(self, conversation_id: str) -> bool:
        """取消当前 generation。

        取消运行中的 asyncio.Task，通过 WebSocketSink 推送 control.cancel 事件。
        """
        task = self._running_tasks.get(conversation_id)
        if task and not task.done():
            task.cancel()
            logger.info("Generation 取消", conversation_id=conversation_id)

            # 通过 WebSocketSink 推送 control.cancel 事件
            cancel_event = RuntimeEvent(
                type="control.cancel",
                payload={"conversation_id": conversation_id, "reason": "user_cancelled"},
            )
            ws_sink = WebSocketSink(conversation_id)
            await ws_sink.emit(cancel_event)

            return True
        return False

    def _on_generation_done(self, conversation_id: str, task: asyncio.Task) -> None:
        """Generation 任务完成回调。"""
        self._running_tasks.pop(conversation_id, None)

        try:
            task.result()
            logger.info("Generation 完成", conversation_id=conversation_id)
        except asyncio.CancelledError:
            logger.info("Generation 被取消", conversation_id=conversation_id)
        except Exception as e:
            logger.error("Generation 异常", conversation_id=conversation_id, error=str(e))

    async def close_session(self, conversation_id: str) -> None:
        """关闭并清理 Session。

        取消运行中的 generation，从内存中移除 Session。
        """
        await self.cancel_generation(conversation_id)
        session = self._sessions.pop(conversation_id, None)
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
