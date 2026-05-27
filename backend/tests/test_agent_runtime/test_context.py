"""
测试上下文管理模块

覆盖 BlackboardManager 和 AgentContextManager。
"""

import pytest

from agent_runtime.context.blackboard import BlackboardManager
from agent_runtime.context.agent_ctx import AgentContextManager, AgentContext, ContextFrame


# ---------------------------------------------------------------------------
# BlackboardManager Tests
# ---------------------------------------------------------------------------

class TestBlackboardManager:
    """测试 BlackboardManager"""

    @pytest.fixture
    def mgr(self):
        return BlackboardManager()

    @pytest.mark.asyncio
    async def test_create(self, mgr):
        bb = await mgr.create("conv_1")
        assert bb["conversation_id"] == "conv_1"
        assert bb["raw_history"] == []
        assert bb["structured_summaries"] == []
        assert bb["kv_state"] == {}
        assert bb["version"] == 0
        assert "created_at" in bb
        assert "updated_at" in bb

    @pytest.mark.asyncio
    async def test_get_from_cache(self, mgr):
        await mgr.create("conv_1")
        bb = await mgr.get("conv_1")
        assert bb is not None
        assert bb["conversation_id"] == "conv_1"

    @pytest.mark.asyncio
    async def test_get_not_found(self, mgr):
        bb = await mgr.get("nonexistent")
        assert bb is None

    @pytest.mark.asyncio
    async def test_append_history(self, mgr):
        await mgr.create("conv_1")
        bb = await mgr.append_history("conv_1", {
            "type": "agent_work",
            "content": "完成代码编写",
        })
        assert len(bb["raw_history"]) == 1
        assert bb["raw_history"][0]["type"] == "agent_work"
        assert bb["version"] == 1
        assert "timestamp" in bb["raw_history"][0]

    @pytest.mark.asyncio
    async def test_append_history_auto_create(self, mgr):
        # 不先 create，直接 append
        bb = await mgr.append_history("conv_2", {
            "type": "user_message",
            "content": "你好",
        })
        assert bb["conversation_id"] == "conv_2"
        assert len(bb["raw_history"]) == 1

    @pytest.mark.asyncio
    async def test_add_summary(self, mgr):
        await mgr.create("conv_1")
        bb = await mgr.add_summary("conv_1", {
            "title": "第一轮总结",
            "content": "已完成需求分析",
        })
        assert len(bb["structured_summaries"]) == 1
        assert bb["structured_summaries"][0]["title"] == "第一轮总结"
        assert bb["version"] == 1

    @pytest.mark.asyncio
    async def test_add_summary_not_found(self, mgr):
        with pytest.raises(ValueError, match="Blackboard not found"):
            await mgr.add_summary("nonexistent", {"title": "test"})

    @pytest.mark.asyncio
    async def test_update_kv(self, mgr):
        await mgr.create("conv_1")
        bb = await mgr.update_kv("conv_1", {"status": "in_progress", "progress": 50})
        assert bb["kv_state"]["status"] == "in_progress"
        assert bb["kv_state"]["progress"] == 50
        assert bb["version"] == 1

        # 再次更新
        bb = await mgr.update_kv("conv_1", {"progress": 75})
        assert bb["kv_state"]["progress"] == 75
        assert bb["kv_state"]["status"] == "in_progress"  # 未覆盖
        assert bb["version"] == 2

    @pytest.mark.asyncio
    async def test_get_raw_history(self, mgr):
        await mgr.create("conv_1")
        for i in range(5):
            await mgr.append_history("conv_1", {"type": "test", "idx": i})

        history = await mgr.get_raw_history("conv_1")
        assert len(history) == 5

        limited = await mgr.get_raw_history("conv_1", limit=2)
        assert len(limited) == 2
        assert limited[0]["idx"] == 3
        assert limited[1]["idx"] == 4

    @pytest.mark.asyncio
    async def test_get_all_summaries(self, mgr):
        await mgr.create("conv_1")
        await mgr.add_summary("conv_1", {"title": "s1"})
        await mgr.add_summary("conv_1", {"title": "s2"})

        summaries = await mgr.get_all_summaries("conv_1")
        assert len(summaries) == 2

    @pytest.mark.asyncio
    async def test_get_kv(self, mgr):
        await mgr.create("conv_1")
        await mgr.update_kv("conv_1", {"key1": "value1", "key2": "value2"})

        all_kv = await mgr.get_kv("conv_1")
        assert all_kv == {"key1": "value1", "key2": "value2"}

        single = await mgr.get_kv("conv_1", "key1")
        assert single == "value1"

        missing = await mgr.get_kv("conv_1", "nonexistent")
        assert missing is None

    @pytest.mark.asyncio
    async def test_get_version(self, mgr):
        await mgr.create("conv_1")
        assert await mgr.get_version("conv_1") == 0
        await mgr.append_history("conv_1", {"type": "test"})
        assert await mgr.get_version("conv_1") == 1


# ---------------------------------------------------------------------------
# AgentContext Tests
# ---------------------------------------------------------------------------

class TestAgentContext:
    """测试 AgentContext"""

    def test_init(self):
        ctx = AgentContext(agent_id="coder", conversation_id="conv_1")
        assert ctx.agent_id == "coder"
        assert ctx.conversation_id == "conv_1"
        assert ctx.stack == []
        assert ctx.current_round == 0

    def test_push_pop(self):
        ctx = AgentContext("coder", "conv_1")
        ctx.push("task", "实现登录功能")
        ctx.push("thought", "需要分析需求")

        assert len(ctx.stack) == 2

        top = ctx.pop()
        assert top.frame_type == "thought"
        assert top.content == "需要分析需求"

        assert len(ctx.stack) == 1

    def test_peek(self):
        ctx = AgentContext("coder", "conv_1")
        ctx.push("task", "任务A")
        ctx.push("thought", "思考A")

        assert ctx.peek().content == "思考A"
        assert ctx.peek("task").content == "任务A"
        assert ctx.peek("nonexistent") is None

    def test_get_full_context(self):
        ctx = AgentContext("coder", "conv_1")
        ctx.system_prompt = "你是一个程序员。"
        ctx.push("task", "写代码")
        ctx.push("thought", "好的")

        text = ctx.get_full_context()
        assert "你是一个程序员" in text
        assert "写代码" in text
        assert "好的" in text

    def test_archive(self):
        ctx = AgentContext("coder", "conv_1")
        ctx.push("task", "任务")
        archive = ctx.archive()
        assert archive["agent_id"] == "coder"
        assert len(archive["stack"]) == 1
        assert "archived_at" in archive

    def test_clear(self):
        ctx = AgentContext("coder", "conv_1")
        ctx.push("task", "任务")
        assert len(ctx.stack) == 1
        ctx.clear()
        assert len(ctx.stack) == 0


# ---------------------------------------------------------------------------
# AgentContextManager Tests
# ---------------------------------------------------------------------------

class TestAgentContextManager:
    """测试 AgentContextManager"""

    @pytest.fixture
    def mgr(self):
        return AgentContextManager()

    def test_initialize(self, mgr):
        mgr.initialize("coder", "conv_1", system_prompt="你是一个程序员。", role_config={"name": "程序员"})
        ctx = mgr.get("coder", "conv_1")
        assert ctx.system_prompt == "你是一个程序员。"
        assert ctx.role_config == {"name": "程序员"}

    def test_get_auto_initialize(self, mgr):
        ctx = mgr.get("coder", "conv_1")
        assert ctx.agent_id == "coder"
        assert ctx.conversation_id == "conv_1"

    def test_after_round(self, mgr):
        mgr.initialize("coder", "conv_1", system_prompt="prompt")
        mgr.get("coder", "conv_1").push("task", "任务")

        archive = mgr.after_round("coder", "conv_1", archive=True)
        assert archive is not None
        assert archive["agent_id"] == "coder"

        # 清理后 stack 为空
        ctx = mgr.get("coder", "conv_1")
        assert len(ctx.stack) == 0

    def test_after_round_no_archive(self, mgr):
        mgr.initialize("coder", "conv_1")
        mgr.get("coder", "conv_1").push("task", "任务")

        archive = mgr.after_round("coder", "conv_1", archive=False)
        assert archive is None
