"""
[LEGACY] 模型网关，用于按 ModelConfig 流式/非流式调用外部 LLM。

.. deprecated::
    该模块已被 `model_provider` 替代，仅保留用于兼容旧代码。
    新代码请使用 model_provider 模块统一接口。
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.errors import NotFoundError, ValidationAppError
from db.models import ModelConfig
from app.services.llm.ark import LLMResult, LLMStreamEvent
from app.services.llm.tool_calls import select_mock_tool_call
from app.services.model_config_resolver import normalize_provider_type
from model_provider.core.interfaces import ChatMessage


async def stream_model_config_chat(
    db: Session,
    model_config_id: str,
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]] | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> AsyncIterator[LLMStreamEvent]:
    """Stream an OpenAI-compatible model config with optional function tools."""

    model = db.get(ModelConfig, model_config_id)
    if not model or model.deleted_at is not None:
        raise NotFoundError("Model config not found")
    provider = model.provider
    if provider.status != "active":
        raise ValidationAppError("Model provider is not active")

    settings = get_settings()
    api_key = provider.api_key_ref
    if api_key == "env:ARK_API_KEY":
        api_key = settings.ark_api_key or os.getenv("ARK_API_KEY")
    if not api_key and provider.base_url.rstrip("/") == settings.ark_base_url.rstrip("/"):
        api_key = settings.ark_api_key or os.getenv("ARK_API_KEY")

    if settings.use_mock_llm or api_key == "mock":
        user_text = next(
            (
                str(message.get("content") or "")
                for message in reversed(messages)
                if message.get("role") == "user"
            ),
            "",
        )
        mock_tool_call = select_mock_tool_call(messages, tools)
        if mock_tool_call:
            yield LLMStreamEvent(
                type="delta",
                text="我将调用已授权工具处理请求。",
                model=model.model_id,
            )
            yield LLMStreamEvent(
                type="tool_calls",
                tool_calls=[mock_tool_call],
                model=model.model_id,
            )
            yield LLMStreamEvent(type="done", usage={}, model=model.model_id)
            return
        text = f"[mock-openai-compatible] {model.name} 已接收提示：{user_text[:120]}"
        for token in text.split(" "):
            yield LLMStreamEvent(type="delta", text=token + " ", model=model.model_id)
            await asyncio.sleep(0.025)
        yield LLMStreamEvent(type="done", usage={}, model=model.model_id)
        return

    if not api_key:
        raise ValidationAppError("Model provider API key is missing; set LLM_PROVIDER=mock for offline demos")

    body: dict[str, Any] = {
        "model": model.model_id,
        "messages": messages,
        "stream": True,
        "stream_options": {"include_usage": True},
        "temperature": model.temperature_default if temperature is None else temperature,
        "max_tokens": min(max_tokens or model.max_output_tokens, model.max_output_tokens, 4096),
    }
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"

    timeout = httpx.Timeout(provider.config.get("timeout_seconds", 60))
    accumulated_tool_calls: dict[int, dict[str, Any]] = {}
    usage: dict[str, Any] | None = None
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream(
            "POST",
            f"{provider.base_url.rstrip('/')}/chat/completions",
            json=body,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        ) as response:
            if response.status_code < 200 or response.status_code >= 300:
                text = await response.aread()
                raise ValidationAppError(
                    json.dumps(
                        {
                            "status": response.status_code,
                            "error": text.decode("utf-8", "replace"),
                            "model": model.model_id,
                            "provider": provider.name,
                        },
                        ensure_ascii=False,
                    )
                )
            async for line in response.aiter_lines():
                line = line.strip()
                if not line or not line.startswith("data:"):
                    continue
                data_text = line.removeprefix("data:").strip()
                if data_text == "[DONE]":
                    break
                try:
                    data = json.loads(data_text)
                except json.JSONDecodeError:
                    continue
                if data.get("usage"):
                    usage = data["usage"]
                    yield LLMStreamEvent(type="usage", usage=usage, model=model.model_id)
                for choice in data.get("choices") or []:
                    delta = choice.get("delta") or {}
                    content = delta.get("content")
                    reasoning_content = delta.get("reasoning_content")
                    if content or reasoning_content:
                        yield LLMStreamEvent(
                            type="delta",
                            text=content or "",
                            reasoning=reasoning_content or "",
                            model=model.model_id,
                        )
                    tool_calls = delta.get("tool_calls")
                    if tool_calls and isinstance(tool_calls, list):
                        for tc_delta in tool_calls:
                            if not isinstance(tc_delta, dict):
                                continue
                            idx = int(tc_delta.get("index", 0) or 0)
                            acc = accumulated_tool_calls.setdefault(idx, {})
                            if "id" in tc_delta:
                                acc["id"] = tc_delta["id"]
                            if "type" in tc_delta:
                                acc["type"] = tc_delta["type"]
                            func = tc_delta.get("function")
                            if isinstance(func, dict):
                                acc.setdefault("function", {})
                                if "name" in func:
                                    acc["function"]["name"] = func["name"]
                                if "arguments" in func:
                                    acc["function"].setdefault("arguments", "")
                                    acc["function"]["arguments"] += func["arguments"]
                    if choice.get("finish_reason") == "tool_calls":
                        yield LLMStreamEvent(
                            type="tool_calls",
                            tool_calls=[
                                {
                                    "id": value.get("id", ""),
                                    "type": value.get("type", "function"),
                                    "function": value.get("function", {}),
                                }
                                for value in accumulated_tool_calls.values()
                                if value.get("function", {}).get("name")
                            ],
                            model=model.model_id,
                        )
                        accumulated_tool_calls = {}
    yield LLMStreamEvent(type="done", usage=usage or {}, model=model.model_id)


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
            provider=normalize_provider_type(provider.provider_type),
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
            provider=normalize_provider_type(provider.provider_type),
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
