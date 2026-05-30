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
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import NotFoundError, ValidationAppError
from app.models import ModelConfig
from app.services.ark import LLMResult, extract_output_text


def _mock_result(model: ModelConfig, prompt: str, reason: str = "mock") -> LLMResult:
    text = f"[mock-openai-compatible] {model.name} 已接收测试提示：{prompt[:120]}"
    return LLMResult(
        text=text,
        model=model.model_id,
        usage={"input_tokens": len(prompt) // 2, "output_tokens": 32},
        raw={"mock": True, "reason": reason},
    )


async def test_model_config(db: AsyncSession, model_config_id: str, prompt: str) -> LLMResult:
    model = await db.get(ModelConfig, model_config_id)
    if not model or model.deleted_at is not None:
        raise NotFoundError("模型配置不存在")
    provider = model.provider
    if provider.status != "active":
        raise ValidationAppError("模型供应商未启用")
    settings = get_settings()
    api_key = provider.api_key_ref
    if api_key == "env:ARK_API_KEY":
        api_key = settings.ark_api_key or os.getenv("ARK_API_KEY")
    if not api_key and provider.base_url.rstrip("/") == settings.ark_base_url.rstrip("/"):
        api_key = settings.ark_api_key or os.getenv("ARK_API_KEY")
    if settings.use_mock_llm or api_key == "mock":
        return _mock_result(model, prompt)
    if not api_key:
        raise ValidationAppError("模型供应商缺少 API Key；如需离线演示请显式设置 LLM_PROVIDER=mock")
    body: dict[str, Any] = {
        "model": model.model_id,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": model.temperature_default,
        "max_tokens": min(model.max_output_tokens, 1024),
    }
    try:
        async with httpx.AsyncClient(timeout=provider.config.get("timeout_seconds", 60)) as client:
            response = await client.post(
                f"{provider.base_url.rstrip('/')}/chat/completions",
                json=body,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            )
    except httpx.HTTPError as exc:
        raise ValidationAppError(f"模型真实连接失败：{exc.__class__.__name__}: {exc}") from exc
    try:
        data = response.json()
    except ValueError:
        data = {"text": response.text}
    if response.status_code < 200 or response.status_code >= 300:
        raise ValidationAppError(json.dumps({"status": response.status_code, "error": data}, ensure_ascii=False))
    return LLMResult(text=extract_output_text(data), model=model.model_id, usage=data.get("usage") or {}, raw=data)


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
    model = await db.get(ModelConfig, model_config_id)
    if not model or model.deleted_at is not None:
        raise NotFoundError("模型配置不存在")
    provider = model.provider
    if provider.status != "active":
        raise ValidationAppError("模型供应商未启用")

    settings = get_settings()
    api_key = provider.api_key_ref
    if api_key == "env:ARK_API_KEY":
        api_key = settings.ark_api_key or os.getenv("ARK_API_KEY")
    if not api_key and provider.base_url.rstrip("/") == settings.ark_base_url.rstrip("/"):
        api_key = settings.ark_api_key or os.getenv("ARK_API_KEY")

    if settings.use_mock_llm or api_key == "mock":
        text = f"[mock-openai-compatible] {model.name} 已接收测试提示：{prompt[:120]}"
        for token in text.split(" "):
            yield {"text": token + " "}
            await asyncio.sleep(0.025)
        return

    if not api_key:
        raise ValidationAppError("模型供应商缺少 API Key；如需离线演示请显式设置 LLM_PROVIDER=mock")

    body: dict[str, Any] = {
        "model": model.model_id,
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
        "stream_options": {"include_usage": True},
        "temperature": model.temperature_default,
        "max_tokens": min(model.max_output_tokens, 1024),
    }

    timeout = httpx.Timeout(provider.config.get("timeout_seconds", 60))
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
                for choice in data.get("choices") or []:
                    delta = choice.get("delta") or {}
                    content = delta.get("content")
                    if content:
                        yield {"text": content}
