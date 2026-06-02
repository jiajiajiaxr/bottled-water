"""测试 ConversationSessionManager"""

import pytest

from app.services.conversation_session_manager import (
    ConversationSessionManager,
    SessionNotFoundError,
    SessionAlreadyRunningError,
)


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