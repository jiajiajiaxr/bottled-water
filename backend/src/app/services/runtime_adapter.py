"""
agent_runtime 适配器层

将新 agent_runtime 运行时桥接到现有 app 层：
- ToolExecutorAdapter: 复用旧的 build_tools_for_agent / execute_tool_by_name
- EventBusSink: 桥接 agent_runtime.Event 到现有 event_bus
- SQLAlchemyPersistenceBackend: 桥接数据库持久化
- OrchestratorV2: 暴露与旧 run_orchestration 兼容的入口
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from common.logger import get_logger
from agent_runtime.core.interfaces import PersistenceBackend, EventSink, ToolExecutor
from agent_runtime.core.types import Event, Message as RuntimeMessage, AgentConfig
from agent_runtime.runtime.session import Session as AgentSession
from agent_runtime.strategies.tech_lead import TechLeadScheduler
from model_provider.core.config import ModelConfig
from model_provider.factory import create_provider

from app.models import Agent, Conversation, Message
from app.services.events import event_bus

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# ToolExecutorAdapter
# ---------------------------------------------------------------------------

class ToolExecutorAdapter(ToolExecutor):
    """工具执行器适配器

    将 agent_runtime 的 ToolExecutor 接口桥接到旧的
    build_tools_for_agent / execute_tool_by_name 系统。
    """

    def __init__(
        self,
        db: Session,
        agent: Agent,
        user: Any,
        conversation: Conversation,
    ):
        self.db = db
        self.agent = agent
        self.user = user
        self.conversation = conversation
        self._tools_cache: Optional[List[Dict]] = None

    def list_tools(self) -> List[Dict]:
        """列出可用工具（OpenAI Function Calling 格式）"""
        if self._tools_cache is None:
            from app.services.agentic_runtime import build_tools_for_agent
            self._tools_cache = build_tools_for_agent(self.db, self.agent)
        return self._tools_cache

    async def execute(self, tool_name: str, parameters: Dict[str, Any]) -> Any:
        """执行工具调用"""
        from app.services.agentic_runtime import execute_tool_by_name

        logger.info("适配器执行工具", tool=tool_name, agent=self.agent.name)
        result = await execute_tool_by_name(
            self.db,
            agent=self.agent,
            user=self.user,
            conversation=self.conversation,
            tool_name=tool_name,
            arguments=parameters,
        )
        return result


# ---------------------------------------------------------------------------
# EventBusSink
# ---------------------------------------------------------------------------

class EventBusSink(EventSink):
    """事件总线接收器

    将 agent_runtime.Event 桥接到现有 event_bus 系统。
    """

    def __init__(self, conversation_id: str):
        self.channel = f"conversation:{conversation_id}"

    async def emit(self, event: Event) -> None:
        """发射单个事件到 event_bus"""
        payload = self._convert_event(event)
        if payload:
            await event_bus.publish(self.channel, payload["type"], payload["data"])

    async def emit_batch(self, events: List[Event]) -> None:
        """批量发射事件"""
        for event in events:
            await self.emit(event)

    def _convert_event(self, event: Event) -> Optional[Dict[str, Any]]:
        """将 agent_runtime Event 转换为 event_bus 格式"""
        event_type = event.type
        payload = event.payload

        # 事件类型映射
        type_map = {
            "session_started": "orchestrator:started",
            "session_completed": "orchestrator:completed",
            "session_error": "orchestrator:error",
            "round_started": "orchestrator:round",
            "scheduling_decision": "orchestrator:decision",
            "agent_started": "agent:started",
            "agent_completed": "agent:completed",
            "agent_failed": "agent:failed",
            "tool_calls_executed": "tool:finished",
            "watchdog_triggered": "orchestrator:watchdog",
            "user_input_received": "orchestrator:user_input",
            "escalation": "orchestrator:escalation",
            "waiting_for_user_input": "orchestrator:waiting",
        }

        mapped_type = type_map.get(event_type, event_type)
        return {"type": mapped_type, "data": payload}


# ---------------------------------------------------------------------------
# SQLAlchemyPersistenceBackend
# ---------------------------------------------------------------------------

class SQLAlchemyPersistenceBackend(PersistenceBackend):
    """SQLAlchemy 持久化后端

    将 agent_runtime 的 PersistenceBackend 接口桥接到现有数据库。
    """

    def __init__(self, db: Session):
        self.db = db

    async def create_conversation(self, metadata: dict) -> str:
        """创建会话"""
        # 复用现有 Conversation 创建逻辑
        return metadata.get("id", "")

    async def load_messages(self, conversation_id: str, limit: int = 100) -> List[RuntimeMessage]:
        """加载消息历史"""
        from app.services.serialization import message_to_dict

        messages = self.db.query(Message).filter(
            Message.conversation_id == conversation_id,
            Message.deleted_at.is_(None),
        ).order_by(Message.created_at.asc()).limit(limit).all()

        result = []
        for msg in messages:
            content = msg.content.get("text", "") if isinstance(msg.content, dict) else str(msg.content)
            result.append(RuntimeMessage(
                id=msg.id,
                conversation_id=msg.conversation_id,
                agent_id=msg.sender_id if msg.sender_type == "agent" else None,
                content=content,
                role="assistant" if msg.sender_type == "agent" else "user",
            ))
        return result

    async def save_message(self, message: RuntimeMessage) -> None:
        """保存单条消息"""
        # agent_runtime 的消息不需要单独保存，由调用方统一处理
        pass

    async def load_blackboard(self, conversation_id: str) -> dict:
        """加载 Blackboard 数据"""
        # 从 Conversation.extra 中读取
        conv = self.db.get(Conversation, conversation_id)
        if conv and conv.extra:
            return conv.extra.get("blackboard", {})
        return {}

    async def save_blackboard(self, conversation_id: str, data: dict) -> None:
        """保存 Blackboard 数据"""
        conv = self.db.get(Conversation, conversation_id)
        if conv:
            conv.extra = {**(conv.extra or {}), "blackboard": data}
            self.db.commit()

    async def load_agent_context(self, agent_id: str, conversation_id: str) -> List[dict]:
        """加载 Agent 上下文"""
        conv = self.db.get(Conversation, conversation_id)
        if conv and conv.extra:
            contexts = conv.extra.get("agent_contexts", {})
            return contexts.get(agent_id, [])
        return []

    async def save_agent_context(self, agent_id: str, conversation_id: str, frames: List[dict]) -> None:
        """保存 Agent 上下文"""
        conv = self.db.get(Conversation, conversation_id)
        if conv:
            contexts = conv.extra.get("agent_contexts", {}) if conv.extra else {}
            contexts[agent_id] = frames
            conv.extra = {**(conv.extra or {}), "agent_contexts": contexts}
            self.db.commit()


# ---------------------------------------------------------------------------
# OrchestratorV2
# ---------------------------------------------------------------------------

class OrchestratorV2:
    """新编排器 V2 入口

    使用 agent_runtime 运行时，但暴露与旧 run_orchestration 兼容的接口。
    """

    def __init__(
        self,
        db: Session,
        conversation: Conversation,
        user_message: Message,
    ):
        self.db = db
        self.conversation = conversation
        self.user_message = user_message
        self.channel = f"conversation:{conversation.id}"

    async def run(self) -> None:
        """运行 tech_lead 调度模式的多 Agent 协作"""
        from app.services.agentic_runtime import select_skills, execute_skill

        prompt = self.user_message.content.get("text", "") if isinstance(self.user_message.content, dict) else str(self.user_message.content)

        # 获取参与会话的 Agent
        agents = self._get_conversation_agents()
        if not agents:
            logger.warning("会话没有可用 Agent", conversation_id=self.conversation.id)
            return

        # 获取当前用户
        from app.models import User
        user = self.db.get(User, self.conversation.creator_id)

        # 构建 AgentConfig 列表
        agent_configs = []
        for agent in agents:
            config = AgentConfig(
                id=agent.id,
                name=agent.name,
                system_prompt=(agent.config or {}).get("system_prompt", "") or agent.description or f"你是 {agent.name}。",
                role=agent.type or "worker",
                tools=(agent.config or {}).get("tools", []),
            )
            agent_configs.append(config)

        # 创建模型提供者
        model_provider = self._create_model_provider()

        # 创建调度器
        scheduler = TechLeadScheduler(
            agents={a.id: a for a in agent_configs},
            model_provider=model_provider,
        )

        # 创建适配器
        persistence = SQLAlchemyPersistenceBackend(self.db)
        event_sink = EventBusSink(self.conversation.id)

        # 选择主 Agent 作为工具执行代理
        primary_agent = agents[0]
        tool_executor = ToolExecutorAdapter(self.db, primary_agent, user, self.conversation)

        # 创建并运行 Session
        session = AgentSession.create(
            agents=agent_configs,
            scheduler=scheduler,
            model_provider=model_provider,
            persistence=persistence,
            event_sink=event_sink,
            tool_executor=tool_executor,
        )

        logger.info("OrchestratorV2 启动", session_id=session.session_id, agent_count=len(agent_configs))

        try:
            async for event in session.run(prompt):
                logger.debug("OrchestratorV2 事件", type=event.type, payload_keys=list(event.payload.keys()))
        except Exception as e:
            logger.error("OrchestratorV2 运行失败", error=str(e), exc_info=True)
            await event_bus.publish(self.channel, "orchestrator:error", {
                "error": str(e),
                "error_type": type(e).__name__,
            })
            raise

        logger.info("OrchestratorV2 完成", session_id=session.session_id)

    def _get_conversation_agents(self) -> List[Agent]:
        """获取会话中的 Agent"""
        from sqlalchemy import select
        from app.models import ConversationParticipant

        participant_agent_ids = [
            item.agent_id
            for item in self.db.scalars(
                select(ConversationParticipant).where(
                    ConversationParticipant.conversation_id == self.conversation.id,
                    ConversationParticipant.participant_type == "agent",
                    ConversationParticipant.left_at.is_(None),
                    ConversationParticipant.agent_id.is_not(None),
                )
            ).all()
            if item.agent_id
        ]

        base_query = select(Agent).where(Agent.deleted_at.is_(None), Agent.status.in_(["online", "degraded"]))
        if participant_agent_ids:
            agents = self.db.scalars(base_query.where(Agent.id.in_(participant_agent_ids))).all()
            order = {agent_id: index for index, agent_id in enumerate(participant_agent_ids)}
            return sorted(agents, key=lambda a: order.get(a.id, 999))
        return self.db.scalars(base_query.where(Agent.type != "custom")).all()

    def _create_model_provider(self):
        """创建模型提供者"""
        # TODO: 从 Conversation 或系统配置中读取模型配置
        # 简化版：使用默认 Ark 配置
        from app.core.config import get_settings
        settings = get_settings()

        # 尝试从环境或配置中获取
        api_key = getattr(settings, "ARK_API_KEY", "")
        model = getattr(settings, "ARK_DEFAULT_MODEL", "ep-xxx")

        if not api_key:
            logger.warning("未配置 ARK API Key，使用 mock 提供者")
            # 返回一个 mock provider 用于测试
            return _MockModelProvider()

        return create_provider(ModelConfig(
            provider="ark",
            model=model,
            api_key=api_key,
        ))


# ---------------------------------------------------------------------------
# Mock Model Provider（用于测试/降级）
# ---------------------------------------------------------------------------

class _MockModelProvider(BaseModelProvider):
    """降级用的 mock 模型提供者"""

    def __init__(self):
        super().__init__({"model": "mock"})

    async def chat(self, messages, system_prompt=None, tools=None, temperature=0.7, max_tokens=None):
        from model_provider.core.interfaces import ChatResponse
        return ChatResponse(content="Mock response: 这是一个降级回复。")

    async def chat_stream(self, messages, system_prompt=None, tools=None, temperature=0.7, max_tokens=None):
        from model_provider.core.interfaces import StreamChunk
        yield StreamChunk(content="Mock stream response.")

    def count_tokens(self, text: str) -> int:
        return len(text) // 2 + 10
