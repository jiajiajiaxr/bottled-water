"""
Blackboard 管理器

纯存储层，不做语义理解。
所有语义操作（总结、摘要、提取 KV）由 Lead 负责。
"""

from typing import Dict, Any, List, Optional
from datetime import datetime

from common.logger import get_logger
from ..core.interfaces import PersistenceBackend

logger = get_logger(__name__)


class BlackboardManager:
    """Blackboard 存储管理器"""

    def __init__(self, persistence: Optional[PersistenceBackend] = None):
        self._cache: Dict[str, Any] = {}
        self._persistence = persistence

    # --- 核心 CRUD ---

    async def create(self, conversation_id: str) -> Dict[str, Any]:
        """创建新的 Blackboard"""
        logger.debug("Blackboard 创建", conversation_id=conversation_id)
        blackboard = {
            "id": f"bb_{conversation_id}",
            "conversation_id": conversation_id,
            "raw_history": [],
            "structured_summaries": [],
            "kv_state": {},
            "version": 0,
            "created_at": datetime.utcnow().isoformat(),
            "updated_at": datetime.utcnow().isoformat(),
        }
        await self._persist(blackboard)
        return blackboard

    async def get(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        """获取 Blackboard（优先缓存）"""
        if conversation_id in self._cache:
            return self._cache[conversation_id]
        # TODO: 从持久化加载
        return None

    # --- 写操作 ---

    async def append_history(self, conversation_id: str, entry: Dict[str, Any]) -> Dict[str, Any]:
        """追加原始历史条目"""
        logger.debug("Blackboard 追加历史", conversation_id=conversation_id, entry_type=entry.get("type"))
        blackboard = await self.get(conversation_id)
        if not blackboard:
            blackboard = await self.create(conversation_id)

        blackboard["raw_history"].append({
            **entry,
            "timestamp": datetime.utcnow().isoformat(),
        })
        blackboard["version"] += 1
        blackboard["updated_at"] = datetime.utcnow().isoformat()

        await self._persist(blackboard)
        return blackboard

    async def add_summary(self, conversation_id: str, summary: Dict[str, Any]) -> Dict[str, Any]:
        """添加结构化摘要"""
        logger.info("Blackboard 添加摘要", conversation_id=conversation_id)
        """添加结构化摘要（由 Lead 生成内容，此处只存储）"""
        blackboard = await self.get(conversation_id)
        if not blackboard:
            raise ValueError(f"Blackboard not found for {conversation_id}")

        blackboard["structured_summaries"].append({
            **summary,
            "created_at": datetime.utcnow().isoformat(),
        })
        blackboard["version"] += 1
        blackboard["updated_at"] = datetime.utcnow().isoformat()

        await self._persist(blackboard)
        return blackboard

    async def update_kv(self, conversation_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """更新键值状态"""
        logger.debug("Blackboard 更新 KV", conversation_id=conversation_id, keys=list(updates.keys()))
        blackboard = await self.get(conversation_id)
        if not blackboard:
            raise ValueError(f"Blackboard not found for {conversation_id}")

        blackboard["kv_state"].update(updates)
        blackboard["version"] += 1
        blackboard["updated_at"] = datetime.utcnow().isoformat()

        await self._persist(blackboard)
        return blackboard

    # --- 读操作 ---

    async def get_raw_history(self, conversation_id: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """获取原始历史"""
        blackboard = await self.get(conversation_id)
        if not blackboard:
            return []
        history = blackboard["raw_history"]
        if limit:
            return history[-limit:]
        return history

    async def get_all_summaries(self, conversation_id: str) -> List[Dict[str, Any]]:
        """获取所有结构化摘要"""
        blackboard = await self.get(conversation_id)
        if not blackboard:
            return []
        return blackboard["structured_summaries"]

    async def get_kv(self, conversation_id: str, key: Optional[str] = None):
        """获取键值状态"""
        blackboard = await self.get(conversation_id)
        if not blackboard:
            return {} if key is None else None
        kv = blackboard["kv_state"]
        if key:
            return kv.get(key)
        return kv

    async def get_version(self, conversation_id: str) -> int:
        """获取当前版本号"""
        blackboard = await self.get(conversation_id)
        return blackboard["version"] if blackboard else 0

    # --- 持久化 ---

    async def _persist(self, blackboard: Dict[str, Any]):
        """持久化到存储 + 更新缓存"""
        self._cache[blackboard["conversation_id"]] = blackboard
        if self._persistence:
            try:
                await self._persistence.save_blackboard(
                    blackboard["conversation_id"], blackboard
                )
            except Exception as e:
                logger.error("Blackboard 持久化失败", conversation_id=blackboard["conversation_id"], error=str(e))
