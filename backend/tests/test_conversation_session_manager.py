"""测试 ConversationSessionManager"""

import asyncio
from contextlib import suppress
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from agent_runtime.core.types import Event as RuntimeEvent
from app.services.conversation_session_manager import (
    ConversationSessionManager,
)
from db.base import Base
from db.models import Conversation, User


class _FakeAgentSession:
    def __init__(self, conversation_id: str, *, slow: bool = False):
        self.session_id = conversation_id
        self.slow = slow
        self.agents = {
            "agent-a": SimpleNamespace(id="agent-a", name="Frontend Worker", role="frontend")
        }

    async def run(self, content: str):
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
            assert record["agent_runs"][0]["status"] == "cancelled"
        finally:
            await engine.dispose()
