"""Conversation-level runtime session manager.

The manager owns the long-lived AgentSession cache for each conversation,
starts and cancels generations, queues user inputs, and records runtime events
for recovery.
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
    """Raised when no session is cached for a conversation."""

    pass


class SessionAlreadyRunningError(Exception):
    """Raised when a conversation already has a running generation."""

    pass


class ConversationSessionManager:
    """Conversation-level session manager."""

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
        self._active_user_message_ids: dict[str, str] = {}
        self._queued_inputs: dict[str, list[dict[str, str | bool | None]]] = {}
        self._pending_preview_message_ids: dict[str, list[str]] = {}
        self._latest_thinking: dict[tuple[str, str, str], str] = {}
        self._generation_thinking_enabled: dict[str, bool] = {}
        self._session_factory = session_factory or AsyncSessionLocal

    @classmethod
    def get_instance(cls) -> "ConversationSessionManager":
        """Return the singleton manager."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _get_lock(self, conversation_id: str) -> asyncio.Lock:
        """Return the per-conversation lock."""
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
        """Get or create a cached runtime session."""



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
                raise ValueError(f"Conversation has no available agents: conversation_id={conversation_id}")

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

            # Keep the persisted conversation pointed at the active runtime session.
            conversation.generation_status = "idle"
            conversation.active_session_id = session.session_id
            await db.commit()

            logger.info(
                "Session created",
                conversation_id=conversation_id,
                session_id=session.session_id,
                agent_count=len(agents),
            )
            return session

    async def start_generation(
        self,
        conversation_id: str,
        content: str,
        *,
        runtime_content: str | None = None,
        thinking_enabled: bool = False,
        user_message_id: str | None = None,
    ) -> None:
        """Start a generation if this user message has not already been handled."""
        user_message_key = str(user_message_id or "").strip()
        async with self._get_lock(conversation_id):
            session = self._sessions.get(conversation_id)
            if not session:
                raise SessionNotFoundError(f"Conversation {conversation_id} has no active Session")

            if user_message_key and await self._generation_exists_for_user_message(
                conversation_id,
                user_message_key,
            ):
                logger.info(
                    "Generation duplicate ignored",
                    conversation_id=conversation_id,
                    user_message_id=user_message_key,
                )
                return

            task = self._running_tasks.get(conversation_id)
            if task and not task.done():
                raise SessionAlreadyRunningError(f"Conversation {conversation_id} already has a running generation")

            generation_id = await self._create_generation_record(
                conversation_id,
                session,
                content,
                user_message_id=user_message_key or None,
            )
            self._generation_thinking_enabled[generation_id] = bool(thinking_enabled)
            if user_message_key:
                self._active_user_message_ids[conversation_id] = user_message_key
            context_metadata = self._generation_context_metadata(
                conversation_id,
                content,
                user_message_id=user_message_id,
            )
            task = asyncio.create_task(
                self._run_generation(
                    session,
                    conversation_id,
                    generation_id,
                    runtime_content or content,
                    context_metadata=context_metadata,
                ),
                name=f"generation-{conversation_id}",
            )
            self._running_tasks[conversation_id] = task
            task.add_done_callback(
                lambda t, cid=conversation_id, gid=generation_id: self._on_generation_done(cid, gid, t)
            )

        logger.info("Generation started", conversation_id=conversation_id, content_preview=content[:50])


    async def _run_generation(
        self,
        session: AgentSession,
        conversation_id: str,
        generation_id: str,
        content: str,
        *,
        context_metadata: dict[str, str] | None = None,
    ) -> None:
        """Run a session generation in the background."""



        async for event in session.run(content, context_metadata=context_metadata):
            await self._record_generation_event(conversation_id, generation_id, event)

    async def send_user_input(
        self,
        conversation_id: str,
        content: str,
        *,
        runtime_content: str | None = None,
        thinking_enabled: bool = False,
        user_message_id: str | None = None,
    ) -> None:
        """Send user input to the active session with message-level idempotency."""
        user_message_key = str(user_message_id or "").strip()
        queued_payload: dict[str, str] | None = None
        async with self._get_lock(conversation_id):
            session = self._sessions.get(conversation_id)
            if not session:
                raise SessionNotFoundError(f"Conversation {conversation_id} has no active Session")

            if user_message_key and await self._generation_exists_for_user_message(
                conversation_id,
                user_message_key,
            ):
                logger.info(
                    "User input duplicate ignored",
                    conversation_id=conversation_id,
                    user_message_id=user_message_key,
                )
                return

            task = self._running_tasks.get(conversation_id)
            if task and not task.done():
                logger.info("User input queued", conversation_id=conversation_id, content_preview=content[:50])
                self._queued_inputs.setdefault(conversation_id, []).append(
                    {
                        "content": content,
                        "runtime_content": runtime_content,
                        "thinking_enabled": bool(thinking_enabled),
                        "user_message_id": user_message_key or None,
                    }
                )
                queued_payload = {
                    "conversation_id": conversation_id,
                    "content_preview": content[:80],
                }

        if queued_payload:
            await WebSocketSink(conversation_id).emit(
                RuntimeEvent(type="user.input_queued", payload=queued_payload)
            )
            return

        logger.info("User input starts generation", conversation_id=conversation_id, content_preview=content[:50])
        await self.start_generation(
            conversation_id,
            content,
            runtime_content=runtime_content,
            thinking_enabled=thinking_enabled,
            user_message_id=user_message_id,
        )


    async def cancel_generation(self, conversation_id: str) -> bool:
        """Cancel the active generation."""



        task = self._running_tasks.get(conversation_id)
        if task and not task.done():
            session = self._sessions.get(conversation_id)
            cancel = getattr(session, "cancel", None) if session else None
            if cancel:
                await cancel("user_cancelled")
            task.cancel()
            logger.info("Generation cancellation requested", conversation_id=conversation_id)

            # Broadcast cancellation so all connected clients stop rendering the stream.
            cancel_event = RuntimeEvent(
                type="control.cancel",
                payload={"conversation_id": conversation_id, "reason": "user_cancelled"},
            )
            ws_sink = WebSocketSink(conversation_id)
            await ws_sink.emit(cancel_event)
            generation_id = self._generation_ids.pop(conversation_id, None)
            if generation_id:
                self._pending_preview_message_ids.pop(generation_id, None)
                self._clear_generation_thinking(generation_id)
                self._generation_thinking_enabled.pop(generation_id, None)
                await self._record_generation_event(conversation_id, generation_id, cancel_event)
                await self._finish_generation(
                    conversation_id,
                    generation_id,
                    status="cancelled",
                    error="user_cancelled",
                )
            self._queued_inputs.pop(conversation_id, None)
            self._active_user_message_ids.pop(conversation_id, None)

            return True
        return False

    def _on_generation_done(self, conversation_id: str, generation_id: str, task: asyncio.Task) -> None:
        """Handle generation task completion."""
        self._running_tasks.pop(conversation_id, None)

        try:
            task.result()
            logger.info("Generation completed", conversation_id=conversation_id)
            status = "completed"
            error = None
        except asyncio.CancelledError:
            logger.info("Generation cancelled", conversation_id=conversation_id)
            status = "cancelled"
            error = "cancelled"
        except Exception as e:
            logger.error("Generation failed", conversation_id=conversation_id, error=str(e))
            status = "failed"
            error = str(e)

        if self._generation_ids.get(conversation_id) != generation_id:
            return
        self._generation_ids.pop(conversation_id, None)
        self._active_user_message_ids.pop(conversation_id, None)
        next_input = self._dequeue_next_input(conversation_id)
        try:
            asyncio.create_task(
                self._finish_generation_and_continue(
                    conversation_id,
                    generation_id,
                    status=status,
                    error=error,
                    next_input=next_input,
                )
            )
        except RuntimeError:
            logger.warning("Generation finalization task failed to start", conversation_id=conversation_id)

    async def close_session(self, conversation_id: str) -> None:
        """Close and forget a cached session."""



        await self.cancel_generation(conversation_id)
        session = self._sessions.pop(conversation_id, None)
        self._session_model_config_ids.pop(conversation_id, None)
        self._session_scheduling_strategies.pop(conversation_id, None)
        self._session_runtime_modes.pop(conversation_id, None)
        self._session_workflow_enabled.pop(conversation_id, None)
        generation_id = self._generation_ids.pop(conversation_id, None)
        if generation_id:
            self._pending_preview_message_ids.pop(generation_id, None)
            self._clear_generation_thinking(generation_id)
            self._generation_thinking_enabled.pop(generation_id, None)
        self._queued_inputs.pop(conversation_id, None)
        self._active_user_message_ids.pop(conversation_id, None)
        self._locks.pop(conversation_id, None)

        if session:
            logger.info("Session closed", conversation_id=conversation_id, session_id=session.session_id)

    def get_session_status(self, conversation_id: str) -> dict | None:
        """Return session status if the session exists."""
        session = self._sessions.get(conversation_id)
        if not session:
            return None
        return session.get_status()

    def is_generation_running(self, conversation_id: str) -> bool:
        """Return whether a generation is currently running."""
        task = self._running_tasks.get(conversation_id)
        return task is not None and not task.done()

    @staticmethod
    def _generation_context_metadata(
        conversation_id: str,
        content: str,
        *,
        user_message_id: str | None,
    ) -> dict[str, str]:
        metadata = {
            "conversation_id": str(conversation_id),
            "session_id": str(conversation_id),
            "visible_content": str(content or ""),
        }
        if user_message_id:
            metadata["user_message_id"] = str(user_message_id)
        return metadata

    async def _generation_exists_for_user_message(
        self,
        conversation_id: str,
        user_message_id: str,
    ) -> bool:
        active_user_message_id = self._active_user_message_ids.get(conversation_id)
        if active_user_message_id == user_message_id:
            return True
        if self._queued_user_message_exists(conversation_id, user_message_id):
            return True

        async with self._session_factory() as db:
            conversation = await db.get(Conversation, conversation_id)
            if not conversation:
                return False
            runtime = (conversation.extra or {}).get("runtime") or {}
            for item in runtime.get("generations") or []:
                if str(item.get("user_message_id") or "") == user_message_id:
                    return True
        return False

    def _queued_user_message_exists(self, conversation_id: str, user_message_id: str) -> bool:
        return any(
            str(item.get("user_message_id") or "") == user_message_id
            for item in self._queued_inputs.get(conversation_id, [])
        )

    async def _create_generation_record(
        self,
        conversation_id: str,
        session: AgentSession,
        content: str,
        *,
        user_message_id: str | None = None,
    ) -> str:
        async with self._session_factory() as db:
            generation_id = await create_generation_record(
                db,
                conversation_id,
                session_id=session.session_id,
                agents=session.agents.values(),
                prompt=content,
                user_message_id=user_message_id,
                model_config_id=self._session_model_config_ids.get(conversation_id),
                scheduling_strategy=self._session_scheduling_strategies.get(conversation_id),
                runtime_mode=self._session_runtime_modes.get(conversation_id),
                workflow_enabled=self._session_workflow_enabled.get(conversation_id),
            )
        self._generation_ids[conversation_id] = generation_id
        return generation_id

    def _dequeue_next_input(self, conversation_id: str) -> dict[str, str | bool | None] | None:
        queue = self._queued_inputs.get(conversation_id)
        if not queue:
            return None
        next_input = queue.pop(0)
        if not queue:
            self._queued_inputs.pop(conversation_id, None)
        return next_input

    async def _record_generation_event(
        self,
        conversation_id: str,
        generation_id: str,
        event: RuntimeEvent,
    ) -> None:
        self._collect_preview_message_id(generation_id, event)
        self._collect_thinking(conversation_id, generation_id, event)
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
            event_type = "message:updated" if event.type == "system.agent_completed" else "message:new"
            await sink.emit(RuntimeEvent(type=event_type, payload=message_to_dict(message)))
            await self._publish_pending_preview_messages(sink, conversation_id, generation_id)
        if event.type == "control.watchdog_triggered":
            reason = str((event.payload or {}).get("reason") or "watchdog_triggered")
            if self._generation_ids.get(conversation_id) == generation_id:
                self._generation_ids.pop(conversation_id, None)
                self._pending_preview_message_ids.pop(generation_id, None)
                self._clear_generation_thinking(generation_id)
                self._generation_thinking_enabled.pop(generation_id, None)
                await self._finish_generation(
                    conversation_id,
                    generation_id,
                    status="failed",
                    error=reason,
                )

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

    def _collect_thinking(
        self,
        conversation_id: str,
        generation_id: str,
        event: RuntimeEvent,
    ) -> None:
        if event.type != "agent.thinking":
            return
        payload = event.payload or {}
        agent_id = str(payload.get("agent_id") or "")
        thinking = str(payload.get("thinking") or "").strip()
        if not generation_id or not agent_id or not thinking:
            return
        key = (conversation_id, generation_id, agent_id)
        existing = str(self._latest_thinking.get(key) or "").strip()
        if not existing:
            self._latest_thinking[key] = thinking
            return
        if thinking == existing or existing.endswith(thinking):
            return
        if thinking.startswith(existing):
            self._latest_thinking[key] = thinking
            return
        self._latest_thinking[key] = f"{existing}{thinking}"

    def _clear_generation_thinking(self, generation_id: str) -> None:
        stale_keys = [key for key in self._latest_thinking if key[1] == generation_id]
        for key in stale_keys:
            self._latest_thinking.pop(key, None)

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

    async def _finish_generation_and_continue(
        self,
        conversation_id: str,
        generation_id: str,
        *,
        status: str,
        error: str | None,
        next_input: dict[str, str | None] | None,
    ) -> None:
        await self._finish_generation(
            conversation_id,
            generation_id,
            status=status,
            error=error,
        )
        self._clear_generation_thinking(generation_id)
        if not next_input:
            return

        next_content = str(next_input.get("content") or "").strip()
        next_runtime_content = next_input.get("runtime_content")
        next_thinking_enabled = bool(next_input.get("thinking_enabled"))
        next_user_message_id = next_input.get("user_message_id")
        if not next_content:
            return

        try:
            await self.start_generation(
                conversation_id,
                next_content,
                runtime_content=next_runtime_content,
                thinking_enabled=next_thinking_enabled,
                user_message_id=str(next_user_message_id) if next_user_message_id else None,
            )
        except Exception as exc:
            logger.error("Queued input failed to start", conversation_id=conversation_id, error=str(exc))
            await WebSocketSink(conversation_id).emit(
                RuntimeEvent(
                    type="generation:failed",
                    payload={
                        "conversation_id": conversation_id,
                        "error": str(exc),
                    },
                )
            )

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
        thinking_enabled = self._generation_thinking_enabled.get(generation_id, False)

        agent_id = str(payload.get("agent_id") or "")
        session = self._sessions.get(conversation_id)
        agent = session.agents.get(agent_id) if session and agent_id else None
        agent_name = getattr(agent, "name", None) or str(payload.get("agent_name") or "Agent")
        agent_avatar_url = (
            str((getattr(agent, "model_config", {}) or {}).get("avatar_url") or "")
            or str(payload.get("agent_avatar_url") or payload.get("sender_avatar_url") or "")
            or None
        )
        if event.type == "system.agent_completed":
            persisted = await db.scalar(
                select(Message)
                .where(
                    Message.conversation_id == conversation_id,
                    Message.sender_type == "agent",
                    Message.sender_id == agent_id,
                    Message.extra["runtime_generation_id"].as_string() == generation_id,
                    Message.content["text"].as_string() == work_product,
                    Message.deleted_at.is_(None),
                )
                .order_by(Message.created_at.desc())
            )
            if persisted:
                thinking = self._latest_thinking.get((conversation_id, generation_id, agent_id), "").strip()
                if thinking and isinstance(persisted.content, dict) and not str(persisted.content.get("thinking") or "").strip():
                    persisted.content = {
                        **persisted.content,
                        "thinking": thinking,
                        "thinking_enabled": thinking_enabled,
                    }
                elif isinstance(persisted.content, dict) and persisted.content.get("thinking_enabled") is None:
                    persisted.content = {
                        **persisted.content,
                        "thinking_enabled": thinking_enabled,
                    }
                if agent_avatar_url and not persisted.sender_avatar_url:
                    persisted.sender_avatar_url = agent_avatar_url
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
        thinking = self._latest_thinking.get((conversation_id, generation_id, agent_id), "").strip()
        message = Message(
            conversation_id=conversation_id,
            sender_type="agent",
            sender_id=agent_id or None,
            sender_name=agent_name,
            sender_avatar_url=agent_avatar_url,
            content_type="text",
            content={
                "text": work_product,
                "thinking": thinking,
                "thinking_enabled": thinking_enabled,
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
        self._generation_thinking_enabled.pop(generation_id, None)
