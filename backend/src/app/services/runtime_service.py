"""
运行时服务 - 统一编排入口

管理 agent_runtime Session 的生命周期，统一 tech_lead 调度策略。
"""

from __future__ import annotations

from typing import Any, AsyncIterator, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from agent_runtime import AgentConfig, Session as AgentSession
from agent_runtime.core.interfaces import ToolExecutor
from agent_runtime.core.types import Event
from agent_runtime.strategies.tech_lead import TechLeadScheduler
from agent_runtime.strategies.single_agent import SingleAgentScheduler
from model_provider import create_provider
from model_provider.core.config import ModelConfig
from model_provider.core.interfaces import BaseModelProvider, ChatMessage, ChatResponse, StreamChunk

from app.core.config import get_settings
from app.models import Agent, Conversation, Message, User
from app.persistence.sqlalchemy_backend import SQLAlchemyBackend
from app.events import SseSink
from app.events import app_event_bus as event_bus
from app.services.serialization import message_meta_to_dict
from common.logger import get_logger

logger = get_logger("app.services.runtime_service")


class _MockModelProvider(BaseModelProvider):
    """Mock 模型提供者，用于单 Agent 纯代码模式（不实际调用 LLM）"""

    def __init__(self):
        super().__init__({"model": "mock"})

    async def chat(
        self,
        messages: List[ChatMessage],
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict]] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> ChatResponse:
        last_message = messages[-1] if messages else None
        content = last_message.content if last_message else "Mock response"
        return ChatResponse(
            content=content,
            finish_reason="stop",
        )

    async def chat_stream(
        self,
        messages: List[ChatMessage],
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict]] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[StreamChunk]:
        last_message = messages[-1] if messages else None
        content = last_message.content if last_message else "Mock response"
        yield StreamChunk(
            content=content,
            finish_reason="stop",
        )


class OrchestratorService:
    """
    统一编排服务。

    根据 Agent 数量自动选择调度器：
    - 单 Agent：SingleAgentScheduler（纯代码，无 LLM 开销）
    - 多 Agent：TechLeadScheduler（LLM 驱动的协调调度）
    """

    @staticmethod
    async def _get_conversation_agents(db: AsyncSession, conversation: Conversation) -> list[Agent]:
        """获取会话中的 Agent"""
        from app.models import ConversationParticipant

        participant_agent_ids = [
            item.agent_id
            for item in (
                await db.scalars(
                    select(ConversationParticipant).where(
                        ConversationParticipant.conversation_id == conversation.id,
                        ConversationParticipant.participant_type == "agent",
                        ConversationParticipant.left_at.is_(None),
                        ConversationParticipant.agent_id.is_not(None),
                    )
                )
            ).all()
            if item.agent_id
        ]
        base_query = select(Agent).where(Agent.deleted_at.is_(None), Agent.status.in_(["online", "degraded"]))
        if participant_agent_ids:
            agents = (await db.scalars(base_query.where(Agent.id.in_(participant_agent_ids)))).all()
            order = {agent_id: index for index, agent_id in enumerate(participant_agent_ids)}
            return sorted(agents, key=lambda a: order.get(a.id, 999))
        return (await db.scalars(base_query.where(Agent.type != "custom"))).all()

    @staticmethod
    def _create_model_provider(agent: Agent | None = None) -> Any:
        """创建模型提供者（默认配置，用于无 model_config_id 时）"""
        settings = get_settings()
        api_key = getattr(settings, "ark_api_key", "") or ""
        model = getattr(settings, "ark_model", "ep-xxx") or "ep-xxx"

        if not api_key:
            logger.warning("未配置 ARK API Key，使用 mock 提供者")
            return _MockModelProvider()

        from model_provider.core.config import ModelConfig as MPModelConfig
        return create_provider(MPModelConfig(provider="ark", model=model, api_key=api_key))

    @staticmethod
    async def create_provider_from_config(db: AsyncSession, model_config_id: str) -> Any:
        """根据 ModelConfig 创建模型提供者"""
        from app.models import ModelConfig as DBModelConfig
        from model_provider.core.config import ModelConfig as MPModelConfig

        config = await db.get(DBModelConfig, model_config_id)
        if not config or config.deleted_at is not None:
            logger.warning(f"ModelConfig not found: {model_config_id}")
            return OrchestratorService._create_model_provider()

        provider = config.provider
        if not provider or provider.status != "active":
            logger.warning(f"Provider not active for config: {model_config_id}")
            return OrchestratorService._create_model_provider()

        api_key_ref = provider.api_key_ref
        api_key = ""
        if api_key_ref == "env:ARK_API_KEY":
            settings = get_settings()
            api_key = getattr(settings, "ark_api_key", "") or ""
        elif api_key_ref and api_key_ref != "mock":
            # 实际应该从密钥管理服务获取，这里简化处理
            api_key = api_key_ref

        if not api_key:
            logger.warning(f"No API key for provider: {provider.name}")
            return OrchestratorService._create_model_provider()

        return create_provider(MPModelConfig(
            provider=provider.provider_type or "ark",
            model=config.model_id,
            api_key=api_key,
            base_url=provider.base_url or None,
        ))

    @staticmethod
    async def run(db: AsyncSession, conversation: Conversation, message: Message, strategy: str, model_config_id: str | None = None) -> None:
        """运行编排

        Args:
            model_config_id: 用户选择的模型配置ID，优先于 agent 配置
        """
        agents = await OrchestratorService._get_conversation_agents(db, conversation)
        if not agents:
            logger.warning(f"会话没有可用 Agent conversation_id={conversation.id}")
            return

        agent_count = len(agents)

        if agent_count == 1:
            await SingleAgentOrchestrator(db, conversation, message, str(conversation.id), agents, model_config_id).run()
        else:
            await TechLeadOrchestrator(db, conversation, message, str(conversation.id), agents, model_config_id).run()


class _ToolExecutorAdapter(ToolExecutor):
    """ToolExecutor 适配器，将 agent_runtime 的工具执行请求路由到 app 层工具注册表"""

    def __init__(self, db: AsyncSession, agent: Agent, user: User, conversation: Conversation):
        self.db = db
        self.agent = agent
        self.user = user
        self.conversation = conversation

    async def list_tools(self) -> list[dict]:
        from app.services.agentic_runtime import build_tools_for_agent
        return await build_tools_for_agent(self.db, self.agent)

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


class SingleAgentOrchestrator:
    """单 Agent 编排器，使用 SingleAgentScheduler（纯代码，无 LLM 开销）"""

    def __init__(self, db: AsyncSession, conversation: Conversation, message: Message, channel: str, agents: list[Agent], model_config_id: str | None = None):
        self.db = db
        self.conversation = conversation
        self.message = message
        self.channel = channel
        self.agents = agents
        self.model_config_id = model_config_id

    async def run(self) -> None:
        agent = self.agents[0]
        user = await self.db.get(User, self.conversation.creator_id)
        agent_config = AgentConfig(
            id=agent.id,
            name=agent.name,
            system_prompt=(agent.config or {}).get("system_prompt", "") or agent.description or f"你是 {agent.name}。",
            role=agent.type or "worker",
            tools=(agent.config or {}).get("tools", []),
        )

        if self.model_config_id:
            model_provider = await OrchestratorService.create_provider_from_config(self.db, self.model_config_id)
        else:
            model_provider = OrchestratorService._create_model_provider(agent)
        scheduler = SingleAgentScheduler(agents={agent.id: agent_config})
        tool_executor = _ToolExecutorAdapter(self.db, agent, user, self.conversation)

        session = AgentSession.create(
            agents=[agent_config],
            scheduler=scheduler,
            model_provider=model_provider,
            persistence=SQLAlchemyBackend(self.db),
            event_sink=SseSink(conversation_id=str(self.conversation.id)),
            tool_executor=tool_executor,
        )

        logger.info(f"SingleAgentOrchestrator 启动 session_id={session.session_id} agent_id={agent.id}")

        prompt = (
            self.message.content.get("text", "")
            if isinstance(self.message.content, dict)
            else str(self.message.content)
        )

        try:
            async for event in session.run(prompt):
                logger.debug(f"SingleAgentOrchestrator 事件 type={event.type}")
                await event_bus.publish(self.channel, event.type, event.payload)
        except Exception as e:
            logger.error(f"SingleAgentOrchestrator 运行失败 error={str(e)}")
            await event_bus.publish(self.channel, "orchestrator:error", {"error": str(e), "error_type": type(e).__name__})
            raise

        await event_bus.publish(self.channel, "orchestrator:complete", {"session_id": session.session_id})


class TechLeadOrchestrator:
    """多 Agent 编排器，使用 TechLeadScheduler（LLM 驱动协调）"""

    def __init__(self, db: AsyncSession, conversation: Conversation, message: Message, channel: str, agents: list[Agent], model_config_id: str | None = None):
        self.db = db
        self.conversation = conversation
        self.message = message
        self.channel = channel
        self.agents = agents
        self.model_config_id = model_config_id

    async def run(self) -> None:
        agents = self.agents
        user = await self.db.get(User, self.conversation.creator_id)
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

        if self.model_config_id:
            model_provider = await OrchestratorService.create_provider_from_config(self.db, self.model_config_id)
        else:
            model_provider = OrchestratorService._create_model_provider(agents[0] if agents else None)
        scheduler = TechLeadScheduler(agents={a.id: a for a in agent_configs})
        primary_agent = agents[0]
        tool_executor = _ToolExecutorAdapter(self.db, primary_agent, user, self.conversation)

        session = AgentSession.create(
            agents=agent_configs,
            scheduler=scheduler,
            model_provider=model_provider,
            persistence=SQLAlchemyBackend(self.db),
            event_sink=SseSink(conversation_id=str(self.conversation.id)),
            tool_executor=tool_executor,
        )

        logger.info(f"TechLeadOrchestrator 启动 session_id={session.session_id} agent_count={len(agent_configs)}")

        prompt = (
            self.message.content.get("text", "")
            if isinstance(self.message.content, dict)
            else str(self.message.content)
        )

        try:
            async for event in session.run(prompt):
                logger.debug(f"TechLeadOrchestrator 事件 type={event.type}")
                await event_bus.publish(self.channel, event.type, event.payload)
        except Exception as e:
            logger.error(f"TechLeadOrchestrator 运行失败 error={str(e)}")
            await event_bus.publish(self.channel, "orchestrator:error", {"error": str(e), "error_type": type(e).__name__})
            raise

        await event_bus.publish(self.channel, "orchestrator:complete", {"session_id": session.session_id})