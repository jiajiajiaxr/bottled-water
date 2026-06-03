"""
[LEGACY] 模型网关，用于按 ModelConfig 流式/非流式调用外部 LLM。

.. deprecated::
    该模块已被 `model_provider` 替代，仅保留用于兼容旧代码。
    新代码请使用 model_provider 模块统一接口。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.errors import NotFoundError, ValidationAppError
from db.models import ModelConfig
from app.services.ark import LLMResult
from model_provider.core.interfaces import ChatMessage


def _mock_result(model: ModelConfig, prompt: str, reason: str = "mock") -> LLMResult:
    text = f"[mock-openai-compatible] {model.name} 已接收测试提示：{prompt[:120]}"
    return LLMResult(
        text=text,
        model=model.model_id,
        usage={"input_tokens": len(prompt) // 2, "output_tokens": 32},
        raw={"mock": True, "reason": reason},
    )


async def test_model_config(db: AsyncSession, model_config_id: str, prompt: str) -> LLMResult:
    """测试模型配置（非流式）。"""
    from app.services.model_config_resolver import resolve_api_key
    from model_provider import create_provider
    from model_provider.core.config import ModelConfig as MPModelConfig

    model = await db.scalar(
        select(ModelConfig)
        .options(selectinload(ModelConfig.provider))
        .where(ModelConfig.id == model_config_id, ModelConfig.deleted_at.is_(None))
    )
    if not model:
        raise NotFoundError("模型配置不存在")
    provider = model.provider
    if provider.status != "active":
        raise ValidationAppError("模型供应商未启用")

    settings = get_settings()
    api_key = await resolve_api_key(provider, model)

    if settings.use_mock_llm or api_key == "mock":
        return _mock_result(model, prompt)
    if not api_key:
        raise ValidationAppError("模型供应商缺少 API Key；如需离线演示请显式设置 LLM_PROVIDER=mock")

    mp = create_provider(
        MPModelConfig(
            provider=provider.provider_type or "ark",
            model=model.model_id,
            api_key=api_key,
            base_url=provider.base_url or None,
        ),
    )

    try:
        response = await mp.chat(
            messages=[ChatMessage(role="user", content=prompt)],
            temperature=model.temperature_default,
            max_tokens=min(model.max_output_tokens, 1024),
        )
    except Exception as exc:
        raise ValidationAppError(f"模型真实连接失败：{exc.__class__.__name__}: {exc}") from exc

    return LLMResult(
        text=response.content or "",
        model=model.model_id,
        usage=response.usage or {},
        raw={"content": response.content, "model": response.model},
    )


async def stream_model_config(
    db: AsyncSession,
    model_config_id: str,
    prompt: str,
) -> AsyncIterator[dict[str, Any]]:
    """流式调用模型配置，逐 token 返回生成结果。

    Args:
        db: 数据库会话。
        model_config_id: 模型配置 ID。
        prompt: 提示词。

    Yields:
        包含生成文本片段的字典，如 {"text": "Hello"}。
    """
    from app.services.model_config_resolver import resolve_api_key
    from model_provider import create_provider
    from model_provider.core.config import ModelConfig as MPModelConfig

    model = await db.scalar(
        select(ModelConfig)
        .options(selectinload(ModelConfig.provider))
        .where(ModelConfig.id == model_config_id, ModelConfig.deleted_at.is_(None))
    )
    if not model:
        raise NotFoundError("模型配置不存在")
    provider = model.provider
    if provider.status != "active":
        raise ValidationAppError("模型供应商未启用")

    settings = get_settings()
    api_key = await resolve_api_key(provider, model)

    if settings.use_mock_llm or api_key == "mock":
        text = f"[mock-openai-compatible] {model.name} 已接收测试提示：{prompt[:120]}"
        for token in text.split(" "):
            yield {"text": token + " "}
            await asyncio.sleep(0.025)
        return

    if not api_key:
        raise ValidationAppError("模型供应商缺少 API Key；如需离线演示请显式设置 LLM_PROVIDER=mock")

    mp = create_provider(
        MPModelConfig(
            provider=provider.provider_type or "ark",
            model=model.model_id,
            api_key=api_key,
            base_url=provider.base_url or None,
        ),
    )

    try:
        async for chunk in mp.chat_stream(
            messages=[ChatMessage(role="user", content=prompt)],
            temperature=model.temperature_default,
            max_tokens=min(model.max_output_tokens, 1024),
        ):
            if chunk.content:
                yield {"text": chunk.content}
    except Exception as exc:
        raise ValidationAppError(f"模型流式调用失败：{exc.__class__.__name__}: {exc}") from exc
