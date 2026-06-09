"""测试 ConversationSessionManager"""

import asyncio
from contextlib import suppress
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from agent_runtime.core.protocol import (
    AGENT_REPORT,
    AGENT_STATE_CHANGED,
    SCHEDULER_DECISION,
    SCHEDULER_PLAN,
    SCHEDULER_SUMMARY,
    SYSTEM_SESSION_COMPLETED,
    SYSTEM_SESSION_STARTED,
)
from agent_runtime.core.types import Event as RuntimeEvent
from app.services.conversation_session_manager import (
    ConversationSessionManager,
)
from app.services.chat.user_messages import save_user_message
from app.services.runtime.generation_records import create_generation_record
from db.base import Base
from db.models import Conversation, Message, User


class _FakeAgentSession:
    def __init__(self, conversation_id: str, *, slow: bool = False):
        self.session_id = conversation_id
        self.slow = slow
        self.last_context_metadata = None
        self.agents = {
            "agent-a": SimpleNamespace(id="agent-a", name="Frontend Worker", role="frontend")
        }

    async def run(self, content: str, context_metadata: dict | None = None):
        self.last_context_metadata = context_metadata
        yield RuntimeEvent(
            type="system.agent_started",
            payload={"round": 1, "agent_id": "agent-a", "agent_name": "Frontend Worker", "task": content},
        )
        if self.slow:
            await asyncio.sleep(30)
        yield RuntimeEvent(
            type="control.scheduling_decision",
            payload={
                "round": 1,
                "decision": "assign",
                "target": "agent-a",
                "task": content,
                "rationale": "Frontend Worker 最适合处理该任务",
            },
        )
        yield RuntimeEvent(
            type="system.agent_completed",
            payload={
                "round": 1,
                "agent_id": "agent-a",
                "agent_name": "Frontend Worker",
                "work_product": "已完成前端页面。",
            },
        )

    def get_status(self):
        return {"status": "completed"}


class _FakeLegacyMultiAgentSession:
    def __init__(self, conversation_id: str):
        self.session_id = conversation_id
        self.last_context_metadata = None
        self.agents = {
            "planner": SimpleNamespace(id="planner", name="Planner Agent", role="planner"),
            "writer": SimpleNamespace(id="writer", name="Writer Agent", role="writer"),
            "analyst": SimpleNamespace(id="analyst", name="Analyst Agent", role="analyst"),
        }

    async def run(self, content: str, context_metadata: dict | None = None):
        self.last_context_metadata = context_metadata
        yield RuntimeEvent(
            type="system.session_started",
            payload={"session_id": self.session_id},
        )
        for agent_id, name, work_product in [
            ("planner", "Planner Agent", "已完成发布方案结构、里程碑和负责人拆分。"),
            ("writer", "Writer Agent", "已完成发布公告正文、FAQ 和用户沟通话术。"),
            ("analyst", "Analyst Agent", "已完成上线风险、指标口径和复盘检查表。"),
        ]:
            yield RuntimeEvent(
                type="system.agent_completed",
                payload={
                    "round": 1,
                    "agent_id": agent_id,
                    "agent_name": name,
                    "work_product": work_product,
                    "status_report": {
                        "agent_id": agent_id,
                        "state": "completed",
                        "will": "complete",
                    },
                },
            )
        yield RuntimeEvent(
            type="system.session_completed",
            payload={"session_id": self.session_id},
        )

    def get_status(self):
        return {"status": "completed"}


class _FakeActorSession:
    def __init__(self, conversation_id: str):
        self.session_id = conversation_id
        self.last_context_metadata = None
        self.agents = {
            "frontend": SimpleNamespace(id="frontend", name="Frontend Worker", role="frontend")
        }

    async def run(self, content: str, context_metadata: dict | None = None):
        self.last_context_metadata = context_metadata
        yield RuntimeEvent(
            type=SYSTEM_SESSION_STARTED,
            payload={"session_id": self.session_id, "runtime": "actor"},
        )
        plan = [
            {
                "id": "auto-1",
                "agent_id": "frontend",
                "agent_name": "Frontend Worker",
                "role": "frontend",
                "status": "queued",
                "task": content,
                "expected_outputs": ["HTML page"],
            }
        ]
        yield RuntimeEvent(
            type=SCHEDULER_PLAN,
            payload={"round": 0, "task": content, "plan": plan, "target_agent_ids": ["frontend"]},
        )
        yield RuntimeEvent(
            type=SCHEDULER_DECISION,
            payload={
                "round": 1,
                "plan": plan,
                "summary": {
                    "status": "partial",
                    "task": content,
                    "plan": plan,
                    "pending_agent_ids": ["frontend"],
                },
                "decision": {
                    "decision_type": "assign",
                    "target_agent_id": "frontend",
                    "task_description": content,
                    "rationale": "Frontend is the right worker.",
                },
            },
        )
        yield RuntimeEvent(
            type=AGENT_STATE_CHANGED,
            payload={"agent_id": "frontend", "state": "running", "reason": "assignment_started", "task": content},
        )
        yield RuntimeEvent(
            type=AGENT_REPORT,
            payload={
                "agent_id": "frontend",
                "agent_name": "Frontend Worker",
                "input": {
                    "user_request": content,
                    "assigned_task": content,
                    "plan": plan,
                    "upstream_outputs": {},
                },
                "work_product": "HTML page completed",
                "output": {
                    "work_product": "HTML page completed",
                    "tool_events": [{"round": 1, "results": [{"tool": "artifact.create_html"}]}],
                },
                "tool_events": [{"round": 1, "results": [{"tool": "artifact.create_html"}]}],
                "report": {
                    "agent_id": "frontend",
                    "state": "completed",
                    "will": "complete",
                    "confidence": 0.95,
                    "rationale": "Done",
                },
            },
        )
        yield RuntimeEvent(
            type=SCHEDULER_SUMMARY,
            payload={
                "round": 2,
                "status": "completed",
                "task": content,
                "plan": [{**plan[0], "status": "completed", "output_preview": "HTML page completed"}],
                "agent_outputs": [
                    {
                        "agent_id": "frontend",
                        "status": "completed",
                        "output_preview": "HTML page completed",
                    }
                ],
                "completed_agent_ids": ["frontend"],
                "final_answer": "Frontend Worker: HTML page completed",
            },
        )
        yield RuntimeEvent(
            type=SYSTEM_SESSION_COMPLETED,
            payload={"session_id": self.session_id, "runtime": "actor", "reason": "completed"},
        )

    def get_status(self):
        return {"status": "completed", "runtime": "actor"}


async def _create_runtime_db(tmp_path, conversation_id: str):
    db_url = f"sqlite+aiosqlite:///{(tmp_path / f'{conversation_id}.db').as_posix()}"
    engine = create_async_engine(db_url, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        user = User(
            id=f"user-{conversation_id}",
            email=f"{conversation_id}@example.com",
            username=f"user-{conversation_id}",
            password_hash="x",
            display_name="Runtime Tester",
        )
        conversation = Conversation(
            id=conversation_id,
            creator_id=user.id,
            chat_type="group",
            title="runtime manager",
            extra={},
        )
        session.add_all([user, conversation])
        await session.commit()
    return engine, factory


class TestConversationSessionManagerSingleton:
    """测试单例模式"""

    def test_get_instance_returns_same_instance(self):
        mgr1 = ConversationSessionManager.get_instance()
        mgr2 = ConversationSessionManager.get_instance()
        assert mgr1 is mgr2


class TestConversationSessionManagerLocks:
    """测试并发锁"""

    def test_get_lock_creates_new_lock(self):
        mgr = ConversationSessionManager()
        lock1 = mgr._get_lock("conv_1")
        lock2 = mgr._get_lock("conv_1")
        assert lock1 is lock2

    def test_get_lock_different_conversations(self):
        mgr = ConversationSessionManager()
        lock1 = mgr._get_lock("conv_1")
        lock2 = mgr._get_lock("conv_2")
        assert lock1 is not lock2


class TestConversationSessionManagerStatus:
    """测试状态查询"""

    def test_get_session_status_returns_none_when_no_session(self):
        mgr = ConversationSessionManager()
        status = mgr.get_session_status("nonexistent")
        assert status is None

    def test_is_generation_running_false_when_no_task(self):
        mgr = ConversationSessionManager()
        assert mgr.is_generation_running("nonexistent") is False

    @pytest.mark.asyncio
    async def test_generation_record_is_persisted_until_completed(self, tmp_path):
        conversation_id = "conv-generation-complete"
        engine, factory = await _create_runtime_db(tmp_path, conversation_id)
        try:
            mgr = ConversationSessionManager(session_factory=factory)
            mgr._sessions[conversation_id] = _FakeAgentSession(conversation_id)
            mgr._session_model_config_ids[conversation_id] = "model-doubao"

            await mgr.start_generation(conversation_id, "实现一个前端页面")
            task = mgr._running_tasks[conversation_id]
            await task
            await asyncio.sleep(0.05)

            async with factory() as session:
                conversation = await session.get(Conversation, conversation_id)

            runtime = (conversation.extra or {}).get("runtime") or {}
            record = runtime["generations"][-1]
            assert runtime["active_generation_id"] is None
            assert conversation.generation_status == "idle"
            assert record["status"] == "completed"
            assert record["model_config_id"] == "model-doubao"
            assert record["event_counts"]["system.agent_started"] == 1
            assert record["event_counts"]["system.agent_completed"] == 1
            assert record["decisions"][0]["decision"] == "assign"
            assert record["agent_runs"][0]["status"] == "completed"
            assert record["agent_runs"][0]["output_preview"] == "已完成前端页面。"
        finally:
            await engine.dispose()

    @pytest.mark.asyncio
    async def test_generation_passes_user_message_context_metadata(self, tmp_path):
        conversation_id = "conv-generation-context"
        engine, factory = await _create_runtime_db(tmp_path, conversation_id)
        try:
            mgr = ConversationSessionManager(session_factory=factory)
            session = _FakeAgentSession(conversation_id)
            mgr._sessions[conversation_id] = session

            await mgr.start_generation(
                conversation_id,
                "visible prompt",
                runtime_content="runtime prompt with attachment context",
                user_message_id="msg-1",
            )
            task = mgr._running_tasks[conversation_id]
            await task

            assert session.last_context_metadata == {
                "conversation_id": conversation_id,
                "session_id": conversation_id,
                "visible_content": "visible prompt",
                "user_message_id": "msg-1",
            }
        finally:
            await engine.dispose()

    @pytest.mark.asyncio
    async def test_generation_record_is_cancelled_when_task_is_stopped(self, tmp_path):
        conversation_id = "conv-generation-cancel"
        engine, factory = await _create_runtime_db(tmp_path, conversation_id)
        try:
            mgr = ConversationSessionManager(session_factory=factory)
            mgr._sessions[conversation_id] = _FakeAgentSession(conversation_id, slow=True)

            await mgr.start_generation(conversation_id, "长任务")
            task = mgr._running_tasks[conversation_id]
            await asyncio.sleep(0.05)
            assert await mgr.cancel_generation(conversation_id) is True
            with suppress(asyncio.CancelledError):
                await task
            await asyncio.sleep(0.05)

            async with factory() as session:
                conversation = await session.get(Conversation, conversation_id)

            runtime = (conversation.extra or {}).get("runtime") or {}
            record = runtime["generations"][-1]
            assert runtime["active_generation_id"] is None
            assert conversation.generation_status == "cancelled"
            assert record["status"] == "cancelled"
            assert record["cancelled_at"]
            assert record["event_counts"]["control.cancel"] == 1
            assert record["agent_runs"][0]["status"] == "cancelled"
        finally:
            await engine.dispose()

    @pytest.mark.asyncio
    async def test_cancel_generation_recovers_abandoned_persisted_run(self, tmp_path):
        conversation_id = "conv-generation-abandoned"
        engine, factory = await _create_runtime_db(tmp_path, conversation_id)
        try:
            async with factory() as session:
                generation_id = await create_generation_record(
                    session,
                    conversation_id,
                    session_id="old-process-session",
                    agents=[
                        SimpleNamespace(
                            id="agent-a",
                            name="Frontend Worker",
                            role="frontend",
                        )
                    ],
                    prompt="long task",
                    user_message_id="msg-abandoned",
                )

            mgr = ConversationSessionManager(session_factory=factory)
            assert await mgr.cancel_generation(conversation_id) is True

            async with factory() as session:
                conversation = await session.get(Conversation, conversation_id)

            runtime = (conversation.extra or {}).get("runtime") or {}
            record = runtime["generations"][-1]
            assert runtime["active_generation_id"] is None
            assert conversation.generation_status == "cancelled"
            assert conversation.active_session_id is None
            assert record["id"] == generation_id
            assert record["status"] == "cancelled"
            assert record["error"] == "user_cancelled"
            assert record["agent_runs"][0]["status"] == "cancelled"
        finally:
            await engine.dispose()

    @pytest.mark.asyncio
    async def test_get_or_create_session_ignores_missing_abandoned_generation(self, tmp_path):
        conversation_id = "conv-generation-no-abandoned"
        engine, factory = await _create_runtime_db(tmp_path, conversation_id)
        try:
            mgr = ConversationSessionManager(session_factory=factory)
            runtime_session = _FakeActorSession(conversation_id)

            async with factory() as session:
                conversation = await session.get(Conversation, conversation_id)
                with patch(
                    "app.services.conversation_session_manager.OrchestratorService._get_conversation_agents",
                    return_value=[
                        SimpleNamespace(
                            id="frontend",
                            name="Frontend Worker",
                            role="frontend",
                            type="worker",
                        )
                    ],
                ):
                    with patch(
                        "app.services.conversation_session_manager.OrchestratorService.create_session",
                        return_value=runtime_session,
                    ) as create_session:
                        session_obj = await mgr.get_or_create_session(session, conversation)

            assert session_obj is runtime_session
            assert create_session.await_count == 1
        finally:
            await engine.dispose()

    @pytest.mark.asyncio
    async def test_recover_conversation_clears_stale_completed_active_generation(self, tmp_path):
        conversation_id = "conv-generation-stale-completed"
        engine, factory = await _create_runtime_db(tmp_path, conversation_id)
        try:
            async with factory() as session:
                generation_id = await create_generation_record(
                    session,
                    conversation_id,
                    session_id="old-process-session",
                    agents=[
                        SimpleNamespace(
                            id="agent-a",
                            name="Frontend Worker",
                            role="frontend",
                        )
                    ],
                    prompt="quick task",
                )
                conversation = await session.get(Conversation, conversation_id)
                runtime = dict((conversation.extra or {}).get("runtime") or {})
                generations = list(runtime.get("generations") or [])
                generations[-1] = {**generations[-1], "status": "completed"}
                runtime["generations"] = generations
                runtime["active_generation_id"] = generation_id
                conversation.extra = {**(conversation.extra or {}), "runtime": runtime}
                conversation.generation_status = "running"
                await session.commit()

            mgr = ConversationSessionManager(session_factory=factory)
            assert await mgr.recover_conversation(conversation_id) is True

            async with factory() as session:
                conversation = await session.get(Conversation, conversation_id)

            runtime = (conversation.extra or {}).get("runtime") or {}
            record = runtime["generations"][-1]
            assert runtime["active_generation_id"] is None
            assert conversation.generation_status == "idle"
            assert conversation.active_session_id is None
            assert record["status"] == "completed"
        finally:
            await engine.dispose()

    @pytest.mark.asyncio
    async def test_recover_conversation_persists_visible_interruption_notice(self, tmp_path):
        conversation_id = "conv-generation-stale-running"
        engine, factory = await _create_runtime_db(tmp_path, conversation_id)
        try:
            async with factory() as session:
                generation_id = await create_generation_record(
                    session,
                    conversation_id,
                    session_id="old-process-session",
                    agents=[
                        SimpleNamespace(
                            id="agent-a",
                            name="Frontend Worker",
                            role="frontend",
                        )
                    ],
                    prompt="build chinese chess",
                )

            mgr = ConversationSessionManager(session_factory=factory)
            assert await mgr.recover_conversation(conversation_id) is True
            assert await mgr.recover_conversation(conversation_id) is False

            async with factory() as session:
                messages = (
                    await session.execute(
                        select(Message).where(Message.conversation_id == conversation_id)
                    )
                ).scalars().all()
                conversation = await session.get(Conversation, conversation_id)

            assert len(messages) == 1
            assert messages[0].sender_id == "system"
            assert messages[0].status == "cancelled"
            assert messages[0].extra["runtime_generation_id"] == generation_id
            assert messages[0].extra["runtime_recovery_notice"] is True
            assert "已中断" in messages[0].content["text"]
            assert conversation.generation_status == "cancelled"
            assert conversation.message_count == 1
            assert conversation.last_message_sender == "System"
        finally:
            await engine.dispose()

    @pytest.mark.asyncio
    async def test_actor_runtime_events_are_persisted_for_recovery(self, tmp_path):
        conversation_id = "conv-generation-actor"
        engine, factory = await _create_runtime_db(tmp_path, conversation_id)
        try:
            mgr = ConversationSessionManager(session_factory=factory)
            mgr._sessions[conversation_id] = _FakeActorSession(conversation_id)

            await mgr.start_generation(conversation_id, "build a small html page")
            task = mgr._running_tasks[conversation_id]
            await task
            await asyncio.sleep(0.05)

            async with factory() as session:
                conversation = await session.get(Conversation, conversation_id)

            runtime = (conversation.extra or {}).get("runtime") or {}
            record = runtime["generations"][-1]
            assert record["status"] == "completed"
            assert record["event_counts"][SCHEDULER_PLAN] == 1
            assert record["event_counts"][SCHEDULER_DECISION] == 1
            assert record["event_counts"][SCHEDULER_SUMMARY] == 1
            assert record["event_counts"][AGENT_REPORT] == 1
            assert record["task_plan"][0]["agent_id"] == "frontend"
            assert record["summary"]["status"] == "completed"
            assert record["summary"]["final_answer"] == "Frontend Worker: HTML page completed"
            assert record["decisions"][0]["decision"] == "assign"
            assert record["decisions"][0]["target"] == "frontend"
            assert record["decisions"][0]["summary"]["status"] == "partial"
            assert record["agent_runs"][0]["status"] == "completed"
            assert record["agent_runs"][0]["input"]["user_request"] == "build a small html page"
            assert record["agent_runs"][0]["output"]["work_product"] == "HTML page completed"
            assert record["agent_runs"][0]["tool_count"] == 1
            assert record["agent_runs"][0]["output_preview"] == "HTML page completed"
        finally:
            await engine.dispose()

    @pytest.mark.asyncio
    async def test_scheduler_summary_is_persisted_as_team_leader_message(self, tmp_path):
        conversation_id = "conv-generation-team-leader-summary"
        engine, factory = await _create_runtime_db(tmp_path, conversation_id)
        try:
            mgr = ConversationSessionManager(session_factory=factory)
            event = RuntimeEvent(
                type=SCHEDULER_SUMMARY,
                payload={
                    "round": 2,
                    "status": "completed",
                    "task": "build a page",
                    "completed_agent_ids": ["frontend"],
                    "final_answer": "HTML page completed.",
                    "final_product": {
                        "type": "single",
                        "content": "HTML page completed.",
                        "artifacts": [{"artifact_id": "artifact-1"}],
                    },
                    "compliance_checks": [{"name": "输出格式标准化", "status": "passed"}],
                    "logic_chain": [{"agent_id": "frontend", "status": "closed"}],
                },
            )

            async with factory() as session:
                first = await mgr._persist_scheduler_summary_message(
                    session,
                    conversation_id,
                    "generation-1",
                    event,
                )
            event.payload["final_answer"] = "HTML page completed. Updated."
            async with factory() as session:
                second = await mgr._persist_scheduler_summary_message(
                    session,
                    conversation_id,
                    "generation-1",
                    event,
                )
            async with factory() as session:
                messages = (
                    await session.execute(
                        select(Message).where(Message.conversation_id == conversation_id)
                    )
                ).scalars().all()
                conversation = await session.get(Conversation, conversation_id)

            assert first is not None
            assert second is not None
            assert first.id == second.id
            assert len(messages) == 1
            assert messages[0].sender_id == "team_leader"
            assert messages[0].sender_name == "Team Leader"
            assert messages[0].content["text"] == "HTML page completed. Updated."
            assert messages[0].content["final_product"]["artifacts"][0]["artifact_id"] == "artifact-1"
            assert messages[0].extra["runtime_scheduler_summary"] is True
            assert conversation.message_count == 1
            assert conversation.last_message_sender == "Team Leader"
        finally:
            await engine.dispose()

    @pytest.mark.asyncio
    async def test_scheduler_summary_can_skip_team_leader_message_for_simple_turn(self, tmp_path):
        conversation_id = "conv-generation-team-leader-summary-skipped"
        engine, factory = await _create_runtime_db(tmp_path, conversation_id)
        try:
            mgr = ConversationSessionManager(session_factory=factory)
            event = RuntimeEvent(
                type=SCHEDULER_SUMMARY,
                payload={
                    "round": 1,
                    "status": "completed",
                    "task": "hello",
                    "completed_agent_ids": ["daily"],
                    "publish_message": False,
                    "final_answer": "你好，我在。",
                },
            )

            async with factory() as session:
                message = await mgr._persist_scheduler_summary_message(
                    session,
                    conversation_id,
                    "generation-1",
                    event,
                )
            async with factory() as session:
                messages = (
                    await session.execute(
                        select(Message).where(Message.conversation_id == conversation_id)
                    )
                ).scalars().all()
                conversation = await session.get(Conversation, conversation_id)

            assert message is None
            assert messages == []
            assert conversation.message_count == 0
            assert not conversation.last_message_sender
        finally:
            await engine.dispose()

    @pytest.mark.asyncio
    async def test_legacy_multi_agent_generation_does_not_synthesize_team_leader_summary(self, tmp_path):
        conversation_id = "conv-generation-legacy-team-leader-summary"
        engine, factory = await _create_runtime_db(tmp_path, conversation_id)
        try:
            mgr = ConversationSessionManager(session_factory=factory)
            mgr._sessions[conversation_id] = _FakeLegacyMultiAgentSession(conversation_id)

            await mgr.start_generation(conversation_id, "整理一份产品发布方案")
            await mgr._running_tasks[conversation_id]
            await asyncio.sleep(0.05)

            async with factory() as session:
                messages = (
                    await session.execute(
                        select(Message).where(Message.conversation_id == conversation_id)
                    )
                ).scalars().all()
                conversation = await session.get(Conversation, conversation_id)

            team = [message for message in messages if message.sender_id == "team_leader"]
            assert team == []
            runtime = (conversation.extra or {}).get("runtime") or {}
            record = runtime["generations"][-1]
            assert not record.get("summary")
            assert record["event_counts"].get(SCHEDULER_SUMMARY, 0) == 0
        finally:
            await engine.dispose()

    @pytest.mark.asyncio
    async def test_generation_pushes_authoritative_conversation_snapshots(self, tmp_path):
        conversation_id = "conv-generation-snapshots"
        engine, factory = await _create_runtime_db(tmp_path, conversation_id)
        emitted = []

        async def fake_emit(_sink, event):
            emitted.append(event)

        try:
            mgr = ConversationSessionManager(session_factory=factory)
            mgr._sessions[conversation_id] = _FakeActorSession(conversation_id)

            with patch("app.services.conversation_session_manager.WebSocketSink.emit", new=fake_emit):
                await mgr.start_generation(conversation_id, "build a small html page")
                task = mgr._running_tasks[conversation_id]
                await task
                await asyncio.sleep(0.05)

            snapshots = [event for event in emitted if event.type == "conversation:updated"]
            assert snapshots
            assert snapshots[0].payload["generation_status"] == "running"
            assert snapshots[0].payload["runtime"]["active_generation_id"]
            assert snapshots[-1].payload["generation_status"] == "idle"
            assert snapshots[-1].payload["runtime"]["active_generation_id"] is None
            assert snapshots[-1].payload["runtime"]["generations"][-1]["status"] == "completed"
        finally:
            await engine.dispose()

    @pytest.mark.asyncio
    async def test_report_and_completed_share_stream_message(self, tmp_path):
        conversation_id = "conv-generation-stream-identity"
        engine, factory = await _create_runtime_db(tmp_path, conversation_id)
        try:
            mgr = ConversationSessionManager(session_factory=factory)
            mgr._sessions[conversation_id] = _FakeAgentSession(conversation_id)

            report_event = RuntimeEvent(
                type=AGENT_REPORT,
                payload={
                    "agent_id": "agent-a",
                    "agent_name": "Frontend Worker",
                    "task": "reply to mention",
                    "work_product": "draft answer",
                    "stream_message_id": "stream-agent-a-1",
                    "agent_message_id": "stream-agent-a-1",
                    "report": {
                        "agent_id": "agent-a",
                        "state": "completed",
                        "will": "complete",
                    },
                },
            )
            completed_event = RuntimeEvent(
                type="system.agent_completed",
                payload={
                    "agent_id": "agent-a",
                    "agent_name": "Frontend Worker",
                    "work_product": "final answer",
                    "stream_message_id": "stream-agent-a-1",
                    "agent_message_id": "stream-agent-a-1",
                    "status_report": {
                        "agent_id": "agent-a",
                        "state": "completed",
                    },
                },
            )

            async with factory() as session:
                first = await mgr._persist_agent_report_message(
                    session,
                    conversation_id,
                    "generation-1",
                    report_event,
                )
            async with factory() as session:
                second = await mgr._persist_agent_report_message(
                    session,
                    conversation_id,
                    "generation-1",
                    completed_event,
                )
            async with factory() as session:
                messages = (
                    await session.execute(
                        select(Message).where(Message.conversation_id == conversation_id)
                    )
                ).scalars().all()

            assert first is not None
            assert second is not None
            assert first.id == second.id
            assert len(messages) == 1
            assert messages[0].content["text"] == "final answer"
            assert messages[0].content["agent_message_id"] == "stream-agent-a-1"
            assert messages[0].content["stream_message_id"] == "stream-agent-a-1"
        finally:
            await engine.dispose()

    @pytest.mark.asyncio
    async def test_generation_start_is_idempotent_for_same_user_message(self, tmp_path):
        conversation_id = "conv-generation-idempotent"
        engine, factory = await _create_runtime_db(tmp_path, conversation_id)
        try:
            mgr = ConversationSessionManager(session_factory=factory)
            mgr._sessions[conversation_id] = _FakeAgentSession(conversation_id)

            await mgr.start_generation(conversation_id, "hello", user_message_id="msg-1")
            await mgr._running_tasks[conversation_id]
            await asyncio.sleep(0.05)

            await mgr.start_generation(conversation_id, "hello", user_message_id="msg-1")

            async with factory() as session:
                conversation = await session.get(Conversation, conversation_id)
            runtime = (conversation.extra or {}).get("runtime") or {}
            assert len(runtime["generations"]) == 1
            assert runtime["generations"][0]["user_message_id"] == "msg-1"
        finally:
            await engine.dispose()

    @pytest.mark.asyncio
    async def test_running_generation_ignores_duplicate_user_message(self, tmp_path):
        conversation_id = "conv-generation-running-duplicate"
        engine, factory = await _create_runtime_db(tmp_path, conversation_id)
        try:
            mgr = ConversationSessionManager(session_factory=factory)
            mgr._sessions[conversation_id] = _FakeAgentSession(conversation_id, slow=True)

            await mgr.start_generation(conversation_id, "long task", user_message_id="msg-1")
            task = mgr._running_tasks[conversation_id]
            await asyncio.sleep(0.05)
            await mgr.send_user_input(conversation_id, "long task", user_message_id="msg-1")

            assert mgr._queued_inputs.get(conversation_id) is None
            assert await mgr.cancel_generation(conversation_id) is True
            with suppress(asyncio.CancelledError):
                await task
        finally:
            await engine.dispose()

    @pytest.mark.asyncio
    async def test_running_generation_queues_distinct_user_message_once(self, tmp_path):
        conversation_id = "conv-generation-queue-dedupe"
        engine, factory = await _create_runtime_db(tmp_path, conversation_id)
        try:
            mgr = ConversationSessionManager(session_factory=factory)
            mgr._sessions[conversation_id] = _FakeAgentSession(conversation_id, slow=True)

            await mgr.start_generation(conversation_id, "first", user_message_id="msg-1")
            task = mgr._running_tasks[conversation_id]
            await asyncio.sleep(0.05)
            await mgr.send_user_input(conversation_id, "second", user_message_id="msg-2")
            await mgr.send_user_input(conversation_id, "second", user_message_id="msg-2")

            assert len(mgr._queued_inputs.get(conversation_id) or []) == 1
            assert await mgr.cancel_generation(conversation_id) is True
            with suppress(asyncio.CancelledError):
                await task
        finally:
            await engine.dispose()

    @pytest.mark.asyncio
    async def test_save_user_message_reuses_client_message_id(self, tmp_path):
        conversation_id = "conv-message-client-id"
        engine, factory = await _create_runtime_db(tmp_path, conversation_id)
        try:
            async with factory() as session:
                user = await session.get(User, f"user-{conversation_id}")
                conversation = await session.get(Conversation, conversation_id)
                payload = {
                    "client_message_id": "client-1",
                    "content": {"text": "hello"},
                }
                first = await save_user_message(session, user=user, conversation=conversation, payload=payload)
                second = await save_user_message(session, user=user, conversation=conversation, payload=payload)

                messages = (
                    await session.execute(select(Message).where(Message.conversation_id == conversation_id))
                ).scalars().all()
                await session.refresh(conversation)

            assert first.id == second.id
            assert len(messages) == 1
            assert conversation.message_count == 1
        finally:
            await engine.dispose()

    @pytest.mark.asyncio
    async def test_same_completion_text_creates_message_per_generation(self, tmp_path):
        conversation_id = "conv-generation-repeat-artifact"
        engine, factory = await _create_runtime_db(tmp_path, conversation_id)
        try:
            mgr = ConversationSessionManager(session_factory=factory)
            mgr._sessions[conversation_id] = _FakeAgentSession(conversation_id)
            event = RuntimeEvent(
                type="system.agent_completed",
                payload={
                    "agent_id": "agent-a",
                    "agent_name": "Frontend Worker",
                    "work_product": "已生成真实 PDF 产物，可在预览卡片中查看和下载。",
                },
            )

            async with factory() as session:
                first = await mgr._persist_agent_report_message(
                    session,
                    conversation_id,
                    "generation-1",
                    event,
                )
            async with factory() as session:
                second = await mgr._persist_agent_report_message(
                    session,
                    conversation_id,
                    "generation-2",
                    event,
                )
            async with factory() as session:
                messages = (
                    await session.execute(
                        select(Message).where(Message.conversation_id == conversation_id)
                    )
                ).scalars().all()

            assert first is not None
            assert second is not None
            assert first.id != second.id
            assert len(messages) == 2
        finally:
            await engine.dispose()
