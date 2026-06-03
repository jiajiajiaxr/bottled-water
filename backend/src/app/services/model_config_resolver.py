"""模型配置解析器 - 统一从数据库读取默认模型配置。

所有业务代码需要创建 model_provider 时，应通过此模块，
不再直接读取环境变量。

.. deprecated::
    环境变量方式已弃用，保留作为 fallback。
    新代码请通过数据库 ModelProvider / ModelConfig 配置。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, AsyncIterator, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from db.models import ModelConfig as DBModelConfig, ModelProvider
from common.logger import get_logger
from model_provider import create_provider
from model_provider.core.config import ModelConfig as MPModelConfig
from model_provider.core.interfaces import (
    BaseModelProvider,
    ChatMessage,
    ChatResponse,
    StreamChunk,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = get_logger(__name__)


async def get_default_model_config(db: AsyncSession) -> tuple[ModelProvider, DBModelConfig] | None:
    """获取默认的 (provider, config) 组合。

    优先级：
    1. 数据库中第一个 active 的 provider + 其第一个 chat 类型的 active config
    2. 环境变量 fallback（deprecated，打 warning 日志）
    3. None（无可用配置）
    """
    provider = await db.scalar(
        select(ModelProvider)
        .where(ModelProvider.status == "active", ModelProvider.deleted_at.is_(None))
        .options(selectinload(ModelProvider.models))
        .order_by(ModelProvider.created_at)
    )
    if provider and provider.models:
        for cfg in provider.models:
            if cfg.status == "active" and cfg.deleted_at is None:
                logger.info(
                    "使用数据库模型配置",
                    provider_id=provider.id,
                    provider_name=provider.name,
                    model_id=cfg.model_id,
                )
                return provider, cfg

    logger.warning(
        "数据库中无可用模型配置，回退到环境变量（已弃用，请在前端设置中配置模型供应商）",
    )
    return None


async def get_model_provider(
    db: AsyncSession, provider_id: str | None = None,
) -> ModelProvider | None:
    """获取模型供应商。provider_id 为 None 时返回默认供应商。"""
    if provider_id:
        return await db.scalar(
            select(ModelProvider).where(
                ModelProvider.id == provider_id,
                ModelProvider.deleted_at.is_(None),
            ),
        )

    result = await get_default_model_config(db)
    return result[0] if result else None


async def resolve_api_key(provider: ModelProvider) -> str:
    """解析供应商的 API Key。

    支持 api_key_ref 格式：
    - "env:XXX" -> 从环境变量读取
    - "mock" -> mock 模式
    - 其他 -> 视为明文 key
    """
    api_key_ref = provider.api_key_ref or ""

    if api_key_ref.startswith("env:"):
        env_name = api_key_ref[4:]
        import os

        settings = get_settings()
        if env_name == "ARK_API_KEY":
            return getattr(settings, "ark_api_key", "") or os.getenv("ARK_API_KEY", "")
        return os.getenv(env_name, "")

    return api_key_ref


class _MockModelProvider(BaseModelProvider):
    """Mock 模型提供者，用于无 LLM 配置时的 fallback。"""

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
        return ChatResponse(content=content, finish_reason="stop")

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
        yield StreamChunk(content=content, finish_reason="stop")


def create_provider_from_env_fallback() -> BaseModelProvider | None:
    """从环境变量创建 provider（deprecated，仅作为 fallback）。"""
    settings = get_settings()
    api_key = getattr(settings, "ark_api_key", "") or ""
    model = getattr(settings, "ark_model", "ep-xxx") or "ep-xxx"

    if not api_key:
        logger.warning("未配置 ARK API Key，使用 mock 提供者")
        return _MockModelProvider()

    return create_provider(
        MPModelConfig(provider="ark", model=model, api_key=api_key),
    )


async def create_provider_from_db(db: AsyncSession) -> BaseModelProvider | None:
    """从数据库创建 provider（推荐方式）。

    无可用数据库配置时，fallback 到环境变量。
    """
    result = await get_default_model_config(db)
    if not result:
        return create_provider_from_env_fallback()

    provider, config = result
    api_key = await resolve_api_key(provider)

    if not api_key:
        logger.warning(f"Provider API Key 为空: {provider.name}")
        return create_provider_from_env_fallback()

    return create_provider(
        MPModelConfig(
            provider=provider.provider_type or "ark",
            model=config.model_id,
            api_key=api_key,
            base_url=provider.base_url or None,
        ),
    )
