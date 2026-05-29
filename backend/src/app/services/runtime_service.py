"""
运行时服务 - 统一编排入口

管理 agent_runtime Session 的生命周期，统一 tech_lead 调度策略。
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from agent_runtime import AgentConfig, Session as AgentSession
from agent_runtime.core.interfaces import ToolExecutor
from agent_runtime.core.types import Event
from agent_runtime.strategies.tech_lead import TechLeadScheduler
from model_provider import create_provider
from model_provider.core.config import ModelConfig

from app.core.config import get_settings
from app.models import Agent, Conversation, Message, User
from app.persistence.sqlalchemy_backend import SQLAlchemyBackend
from app.events.sse_sink import SSEEventSink
from app.services.events import event_bus
from app.services.serialization import message_meta_to_dict

logger = logging.getLogger(__name__)


class OrchestratorService:
    """
    统一编排服务。

    根据 scheduling_strategy 选择调度器：
    - "tech_lead": TechLeadScheduler（基于 agent_runtime Session）
    - "workflow": 已移除，统一使用 Session 模式
    """

    @staticmethod
    def _get_conversation_agents(db: Session, conversation: Conversation) -> list[Agent]:
        """获取会话中的 Agent"""
        from app.models import ConversationParticipant

        participant_agent_ids = [
            item.agent_id
            for item in db.scalars(
                select(ConversationParticipant).where(
                    ConversationParticipant.conversation_id == conversation.id,
                    ConversationParticipant.participant_type == "agent",
                    ConversationParticipant.left_at.is_(None),
                    ConversationParticipant.agent_id.is_not(None),
                )
            ).all()
            if item.agent_id
        ]
        base_query = select(Agent).where(Agent.deleted_at.is_(None), Agent.status.in_(["online", "degraded"]))
        if participant_agent_ids:
            agents = db.scalars(base_query.where(Agent.id.in_(participant_agent_ids))).all()
            order = {agent_id: index for index, agent_id in enumerate(participant_agent_ids)}
            return sorted(agents, key=lambda a: order.get(a.id, 999))
        return db.scalars(base_query.where(Agent.type != "custom")).all()

    @staticmethod
    def _create_model_provider(agent: Agent | None = None) -> Any:
        """创建模型提供者"""
        settings = get_settings()
        api_key = getattr(settings, "ARK_API_KEY", "")
        model = getattr(settings, "ARK_DEFAULT_MODEL", "ep-xxx")

        if not api_key:
            logger.warning("未配置 ARK API Key，使用 mock 提供者")
            return _MockModelProvider()

        return create_provider(ModelConfig(provider="ark", model=model, api_key=api_key))

    @staticmethod
    async def run(db: Session, conversation: Conversation, message: Message, strategy: str) -> None:
        """运行编排"""
        await TechLeadOrchestrator(db, conversation, message, str(conversation.id)).run()


class _ToolExecutorAdapter(ToolExecutor):
    """ToolExecutor 适配器，将 agent_runtime 的工具执行请求路由到 app 层工具注册表"""

    def __init__(self, db: Session, agent: Agent, user: User, conversation: Conversation):
        self.db = db
        self.agent = agent
        self.user = user
        self.conversation = conversation

    def list_tools(self) -> list[dict]:
        from app.services.agentic_runtime import build_tools_for_agent
        return build_tools_for_agent(self.db, self.agent)

    async def execute(self, tool_name: str, parameters: dict) -> Any:
        from app.services.agentic_runtime import execute_tool_by_name
        return await execute_tool_by_name(
            self.db,
            agent=self.agent,
            user=self.user,
            conversation=self.conversation,
            tool_name=tool_name,
            arguments=parameters,
        )


class TechLeadOrchestrator:
    """基于 agent_runtime Session 的编排器（统一入口）"""

    def __init__(self, db: Session, conversation: Conversation, message: Message, channel: str):
        self.db = db
        self.conversation = conversation
        self.message = message
        self.channel = channel

    async def run(self) -> None:
        agents = OrchestratorService._get_conversation_agents(self.db, self.conversation)
        if not agents:
            logger.warning("会话没有可用 Agent", conversation_id=self.conversation.id)
            return

        user = self.db.get(User, self.conversation.creator_id)
        agent_configs = [
            AgentConfig(
                id=agent.id,
                name=agent.name,
                system_prompt=(agent.config or {}).get("system_prompt", "") or agent.description or f"你是 {agent.name}。",
                role=agent.type or "worker",
                tools=(agent.config or {}).get("tools", []),
            )
            for agent in agents
        ]

        model_provider = OrchestratorService._create_model_provider(agents[0] if agents else None)
        scheduler = TechLeadScheduler(agents={a.id: a for a in agent_configs})
        primary_agent = agents[0]
        tool_executor = _ToolExecutorAdapter(self.db, primary_agent, user, self.conversation)

        session = AgentSession.create(
            agents=agent_configs,
            scheduler=scheduler,
            model_provider=model_provider,
            persistence=SQLAlchemyBackend(self.db),
            event_sink=SSEEventSink(conversation_id=str(self.conversation.id)),
            tool_executor=tool_executor,
        )

        logger.info("TechLeadOrchestrator 启动", session_id=session.session_id, agent_count=len(agent_configs))

        prompt = (
            self.message.content.get("text", "")
            if isinstance(self.message.content, dict)
            else str(self.message.content)
        )

        try:
            async for event in session.run(prompt):
                logger.debug("TechLeadOrchestrator 事件", type=event.type)
        except Exception as e:
            logger.error("TechLeadOrchestrator 运行失败", error=str(e), exc_info=True)
            await event_bus.publish(self.channel, "orchestrator:error", {"error": str(e), "error_type": type(e).__name__})
            raise

        logger.info("TechLeadOrchestrator 完成", session_id=session.session_id)