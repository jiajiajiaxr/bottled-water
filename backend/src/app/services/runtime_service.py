"""
运行时服务 - 连接 HTTP 层和 agent_runtime

这是 app 层唯一直接依赖 agent_runtime 的模块。
负责：
- 把数据库对象翻译为运行时对象
- 管理运行时 Session 的生命周期
- 提供事件流给 API 层
"""

from typing import AsyncIterator, Dict, Optional

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from agent_runtime import Session, AgentConfig
from agent_runtime.strategies.tech_lead import TechLeadScheduler
from model_provider.factory import create_provider
from model_provider.core.config import ModelConfig

from common.logger import get_logger
from app.database import get_db
from app.models import Conversation, Agent as DBAgent
from app.persistence.sqlalchemy_backend import SQLAlchemyBackend
from app.events.sse_sink import SSEEventSink

logger = get_logger(__name__)


class RuntimeService:
    """运行时服务"""

    _sessions: Dict[str, Session] = {}

    @classmethod
    async def create_session(
        cls,
        conversation: Conversation,
        db_agents: list[DBAgent],
        db: AsyncSession,
    ) -> Session:
        """从数据库对象创建运行时会话"""

        # 1. 转换 Agent 定义
        runtime_agents = [
            AgentConfig(
                id=str(a.id),
                name=a.name,
                system_prompt=a.config.get("system_prompt", ""),
                role=a.config.get("role", "worker"),
                model_config=a.config.get("model_config", {}),
                tools=a.config.get("tools", []),
            )
            for a in db_agents
        ]

        # 2. 创建模型提供者
        # 优先从 conversation.extra 读取模型配置，否则用第一个 agent 的
        model_config = conversation.extra.get("model_config", {}) if conversation.extra else {}
        if not model_config and db_agents:
            model_config = db_agents[0].config.get("model_config", {})

        provider = create_provider(ModelConfig(**model_config)) if model_config else None
        if not provider:
            raise HTTPException(status_code=400, detail="No model configuration found")

        # 3. 创建调度器
        strategy = (conversation.extra or {}).get("scheduling_strategy", "tech_lead")
        scheduler = cls._create_scheduler(strategy, runtime_agents)

        # 4. 创建 Session
        session = Session.create(
            agents=runtime_agents,
            scheduler=scheduler,
            model_provider=provider,
            persistence=SQLAlchemyBackend(db),
            event_sink=SSEEventSink(conversation_id=str(conversation.id)),
        )

        cls._sessions[session.session_id] = session
        logger.info(
            "运行时 Session 创建",
            session_id=session.session_id,
            conversation_id=str(conversation.id),
            agent_count=len(runtime_agents),
            strategy=strategy,
        )
        return session

    @classmethod
    async def run_session(
        cls,
        session_id: str,
        message: str,
    ) -> AsyncIterator[Event]:
        """运行会话，返回事件流"""
        session = cls._sessions.get(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        async for event in session.run(message):
            yield event

    @classmethod
    def get_session(cls, session_id: str) -> Optional[Session]:
        """获取已创建的会话"""
        return cls._sessions.get(session_id)

    @classmethod
    def remove_session(cls, session_id: str) -> None:
        """移除会话"""
        cls._sessions.pop(session_id, None)

    @classmethod
    def _create_scheduler(cls, strategy: str, agents: list[AgentConfig]):
        """根据策略名称创建调度器"""
        if strategy == "tech_lead":
            return TechLeadScheduler(agents={a.id: a for a in agents})
        # TODO: 扩展更多策略
        # elif strategy == "consensus":
        #     return ConsensusScheduler(agents=agents)
        # elif strategy == "competitive":
        #     return CompetitiveScheduler(agents=agents)
        else:
            return TechLeadScheduler(agents={a.id: a for a in agents})
