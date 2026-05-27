"""
SQLAlchemy 持久化后端实现

把 agent_runtime 的抽象接口桥接到现有的 SQLAlchemy ORM。
"""

from typing import List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from agent_runtime.core.interfaces import PersistenceBackend
from agent_runtime.core.types import Message

from common.logger import get_logger
from app.models import Message as DBMessage, Conversation

logger = get_logger(__name__)


class SQLAlchemyBackend(PersistenceBackend):
    """基于 SQLAlchemy 的持久化实现"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_conversation(self, metadata: dict) -> str:
        """创建会话"""
        conv = Conversation(
            creator_id=metadata.get("creator_id", ""),
            title=metadata.get("title", "New Conversation"),
            chat_type=metadata.get("chat_type", "single"),
            extra=metadata.get("extra", {}),
        )
        self.db.add(conv)
        await self.db.commit()
        await self.db.refresh(conv)
        return str(conv.id)

    async def load_messages(self, conversation_id: str, limit: int = 100) -> List[Message]:
        """加载消息历史"""
        result = await self.db.execute(
            select(DBMessage)
            .where(DBMessage.conversation_id == conversation_id)
            .order_by(DBMessage.created_at.desc())
            .limit(limit)
        )
        db_messages = result.scalars().all()

        return [
            Message(
                id=str(m.id),
                conversation_id=str(m.conversation_id),
                agent_id=str(m.sender_id) if m.sender_type == "agent" else None,
                content=m.content.get("text", ""),
                role="assistant" if m.sender_type == "agent" else "user",
                metadata=m.extra or {},
            )
            for m in db_messages
        ]

    async def save_message(self, message: Message) -> None:
        """保存消息"""
        db_msg = DBMessage(
            id=message.id,
            conversation_id=message.conversation_id,
            sender_type="agent" if message.agent_id else "user",
            sender_id=message.agent_id,
            sender_name=message.metadata.get("sender_name", ""),
            content={"text": message.content},
            extra=message.metadata,
        )
        self.db.add(db_msg)
        await self.db.commit()

    async def load_blackboard(self, conversation_id: str) -> dict:
        """加载 Blackboard（从 conversation.extra 读取）"""
        result = await self.db.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        conv = result.scalar_one_or_none()
        if not conv or not conv.extra:
            return {"raw_history": [], "structured_summaries": [], "kv_state": {}, "version": 0}

        bb = conv.extra.get("blackboard", {})
        return {
            "raw_history": bb.get("raw_history", []),
            "structured_summaries": bb.get("structured_summaries", []),
            "kv_state": bb.get("kv_state", {}),
            "version": bb.get("version", 0),
        }

    async def save_blackboard(self, conversation_id: str, data: dict) -> None:
        """保存 Blackboard（写入 conversation.extra）"""
        result = await self.db.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        conv = result.scalar_one_or_none()
        if conv:
            if not conv.extra:
                conv.extra = {}
            conv.extra["blackboard"] = data
            await self.db.commit()

    async def load_agent_context(self, agent_id: str, conversation_id: str) -> List[dict]:
        """加载 Agent 上下文"""
        # 暂存于 conversation.extra 中
        result = await self.db.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        conv = result.scalar_one_or_none()
        if not conv or not conv.extra:
            return []

        contexts = conv.extra.get("agent_contexts", {})
        return contexts.get(agent_id, [])

    async def save_agent_context(self, agent_id: str, conversation_id: str, frames: List[dict]) -> None:
        """保存 Agent 上下文"""
        result = await self.db.execute(
            select(Conversation).where(Conversation.id == conversation_id)
        )
        conv = result.scalar_one_or_none()
        if conv:
            if not conv.extra:
                conv.extra = {}
            if "agent_contexts" not in conv.extra:
                conv.extra["agent_contexts"] = {}
            conv.extra["agent_contexts"][agent_id] = frames
            await self.db.commit()
