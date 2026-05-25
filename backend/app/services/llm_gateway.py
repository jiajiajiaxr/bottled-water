from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncIterator
from typing import Any

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import NotFoundError, ValidationAppError
from app.models import ModelConfig
from app.services.ark import LLMResult, LLMStreamEvent, extract_output_text


def _mock_result(model: ModelConfig, prompt: str, reason: str = "mock") -> LLMResult:
    text = f"[mock-openai-compatible] {model.name} 已接收测试提示：{prompt[:120]}"
    return LLMResult(
        text=text,
        model=model.model_id,
        usage={"input_tokens": len(prompt) // 2, "output_tokens": 32},
        raw={"mock": True, "reason": reason},
    )


async def test_model_config(db: Session, model_config_id: str, prompt: str) -> LLMResult:
    model = db.get(ModelConfig, model_config_id)
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
    db: Session,
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
    model = db.get(ModelConfig, model_config_id)
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
            (str(message.get("content") or "") for message in reversed(messages) if message.get("role") == "user"),
            "",
        )
        if tools and "file" in user_text.lower():
            yield LLMStreamEvent(type="delta", text="我先读取文件内容。", model=model.model_id)
            yield LLMStreamEvent(
                type="tool_calls",
                tool_calls=[
                    {
                        "id": "call_mock_model_config",
                        "type": "function",
                        "function": {
                            "name": tools[0]["function"]["name"],
                            "arguments": json.dumps({"prompt": user_text}, ensure_ascii=False),
                        },
                    }
                ],
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
