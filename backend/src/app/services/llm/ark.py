"""
[LEGACY] 直接 HTTP 调用火山引擎 Ark API 的客户端。

.. deprecated::
    该模块已被 `model_provider` 替代，仅保留用于兼容旧代码。
    新代码请使用 model_provider 模块：
        from model_provider import create_provider, ModelConfig
        provider = create_provider(ModelConfig(provider="ark", model="...", api_key="..."))
        result = await provider.chat(messages=[...])
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Literal

import httpx

from app.core.config import ROOT_DIR, Settings, get_settings

logger = logging.getLogger(__name__)


class ArkProviderError(RuntimeError):
    pass


@dataclass
class LLMResult:
    text: str
    model: str
    usage: dict[str, Any]
    raw: dict[str, Any]
    provider_status: str = "ok"


@dataclass
class LLMStreamEvent:
    type: Literal["delta", "usage", "done", "error", "tool_calls"]
    text: str = ""
    reasoning: str = ""
    usage: dict[str, Any] | None = None
    error: str | None = None
    model: str | None = None
    tool_calls: list[dict[str, Any]] | None = None


def extract_output_text(data: dict[str, Any]) -> str:
    if isinstance(data.get("output_text"), str):
        return data["output_text"]
    try:
        text = data["choices"][0]["message"]["content"]
        if isinstance(text, str):
            return text
    except (KeyError, IndexError, TypeError):
        pass

    def collect(value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            out: list[str] = []
            for item in value:
                out.extend(collect(item))
            return out
        if isinstance(value, dict):
            item_type = value.get("type")
            if item_type in {"output_text", "text", "input_text"} and isinstance(
                value.get("text"), str
            ):
                return [value["text"]]
            if isinstance(value.get("content"), str):
                return [value["content"]]
            if "content" in value:
                return collect(value["content"])
        return []

    output: list[str] = []
    for item in data.get("output") or []:
        output.extend(collect(item))
    return "".join(output)


class ArkClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.base_url = self.settings.ark_base_url.rstrip("/")

    def _api_key(self) -> str:
        value = (self.settings.ark_api_key or "").strip().strip('"').strip("'")
        if value.lower().startswith("authorization:"):
            value = value.split(":", 1)[1].strip()
        if value.lower().startswith("bearer "):
            value = value[7:].strip()
        value = re.split(
            r"(?=(?:ARK_BASE_URL|ARK_ENDPOINT_ID|ARK_MODEL|ARK_API_KEY|LLM_PROVIDER|DATABASE_URL|REDIS_URL|SECRET_KEY)=)",
            value,
            maxsplit=1,
        )[0].strip()
        return value

    def _auth_error_hint(self, status_code: int, data: Any) -> str:
        return json.dumps(
            {
                "status": status_code,
                "error": data,
                "env_file": str(ROOT_DIR / ".env"),
                "key_loaded": bool(self._api_key()),
                "hint": "后端只读取项目目录 .env；请确认 ARK_API_KEY 是火山方舟 API Key 原值，不要填 AK/SK，也不要带 Authorization/Bearer 前缀。",
            },
            ensure_ascii=False,
        )

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.3,
        max_tokens: int = 1200,
        purpose: str = "chat",
    ) -> LLMResult:
        if self.settings.use_mock_llm:
            return await self._mock_chat(messages, purpose=purpose)
        errors: list[dict[str, Any]] = []
        for model in self.settings.model_candidates:
            try:
                body = {
                    "model": model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                }
                data = await self._post_json("/chat/completions", body)
                return LLMResult(
                    text=extract_output_text(data),
                    model=model,
                    usage=data.get("usage") or {},
                    raw=data,
                )
            except Exception as exc:
                errors.append({"model": model, "error": str(exc)})
        raise ArkProviderError(json.dumps(errors, ensure_ascii=False))

    async def responses(self, input_text: str, *, max_output_tokens: int = 800) -> LLMResult:
        if self.settings.use_mock_llm:
            return LLMResult(
                text=f"[mock] 已完成上下文摘要：{input_text[:120]}",
                model="mock-responses",
                usage={"input_tokens": len(input_text) // 3, "output_tokens": 80},
                raw={"mock": True},
            )
        errors: list[dict[str, Any]] = []
        for model in self.settings.model_candidates:
            try:
                data = await self._post_json(
                    "/responses",
                    {
                        "model": model,
                        "input": input_text,
                        "max_output_tokens": max_output_tokens,
                        "temperature": 0,
                    },
                )
                return LLMResult(
                    text=extract_output_text(data),
                    model=model,
                    usage=data.get("usage") or {},
                    raw=data,
                )
            except Exception as exc:
                errors.append({"model": model, "error": str(exc)})
        raise ArkProviderError(json.dumps(errors, ensure_ascii=False))

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.3,
        max_tokens: int = 1200,
        purpose: str = "chat",
        tools: list[dict[str, Any]] | None = None,
        thinking: dict[str, Any] | None = None,
    ) -> AsyncIterator[LLMStreamEvent]:
        if self.settings.use_mock_llm:
            async for item in self._mock_stream(messages, purpose=purpose, tools=tools):
                yield item
            return
        errors: list[dict[str, Any]] = []
        for model in self.settings.model_candidates:
            try:
                body: dict[str, Any] = {
                    "model": model,
                    "messages": messages,
                    "stream": True,
                    "stream_options": {"include_usage": True},
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                }
                if tools:
                    body["tools"] = tools
                if thinking:
                    body["thinking"] = thinking
                async for item in self._stream_model(model, body):
                    yield item
                return
            except Exception as exc:
                errors.append({"model": model, "error": str(exc)})
        yield LLMStreamEvent(type="error", error=json.dumps(errors, ensure_ascii=False))

    async def complete_stream_chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.3,
        max_tokens: int = 1200,
        purpose: str = "chat",
        tools: list[dict[str, Any]] | None = None,
        thinking: dict[str, Any] | None = None,
    ) -> LLMResult:
        """Use the streaming transport and collect the final text silently."""
        text_parts: list[str] = []
        usage: dict[str, Any] = {}
        model = ""
        raw_events: list[dict[str, Any]] = []

        async for event in self.stream_chat(
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            purpose=purpose,
            tools=tools,
            thinking=thinking,
        ):
            if event.type == "delta":
                if event.text:
                    text_parts.append(event.text)
                if event.reasoning and not event.text:
                    text_parts.append(event.reasoning)
                model = event.model or model
            elif event.type == "usage":
                usage = event.usage or usage
                model = event.model or model
            elif event.type == "done":
                usage = event.usage or usage
                model = event.model or model
            elif event.type == "tool_calls":
                raw_events.append({"type": event.type, "tool_calls": event.tool_calls})
                model = event.model or model
            elif event.type == "error":
                raise ArkProviderError(event.error or "stream_chat failed")

        return LLMResult(
            text="".join(text_parts),
            model=model or "unknown",
            usage=usage,
            raw={"events": raw_events, "purpose": purpose},
        )

    async def _post_json(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        api_key = self._api_key()
        if not api_key:
            raise ArkProviderError("缺少 ARK_API_KEY")
        async with httpx.AsyncClient(timeout=self.settings.ark_timeout_seconds) as client:
            response = await client.post(
                f"{self.base_url}{path}",
                json=body,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            )
        try:
            data = response.json()
        except ValueError:
            data = {"text": response.text}
        if response.status_code < 200 or response.status_code >= 300:
            raise ArkProviderError(self._auth_error_hint(response.status_code, data))
        return data

    async def _stream_model(
        self, model: str, body: dict[str, Any]
    ) -> AsyncIterator[LLMStreamEvent]:
        api_key = self._api_key()
        if not api_key:
            raise ArkProviderError("缺少 ARK_API_KEY")
        usage: dict[str, Any] | None = None
        timeout = httpx.Timeout(self.settings.ark_stream_timeout_seconds)
        # 累积增量 tool_calls：key 为 index，value 为累积后的 tool_call 字典
        accumulated_tool_calls: dict[int, dict[str, Any]] = {}
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                json=body,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
            ) as response:
                if response.status_code < 200 or response.status_code >= 300:
                    text = await response.aread()
                    raise ArkProviderError(self._auth_error_hint(response.status_code, text.decode("utf-8", "replace")))
                line_count = 0
                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data_text = line.removeprefix("data:").strip()
                    if data_text == "[DONE]":
                        break
                    data = json.loads(data_text)
                    line_count += 1
                    if line_count <= 3:
                        logger.info(f"[ark_sse] chunk {line_count}: {json.dumps(data, ensure_ascii=False)[:400]}")
                    if data.get("usage"):
                        usage = data["usage"]
                        yield LLMStreamEvent(type="usage", usage=usage, model=model)
                    for choice in data.get("choices") or []:
                        delta = choice.get("delta") or {}
                        content = delta.get("content")
                        reasoning_content = delta.get("reasoning_content")
                        if content or reasoning_content:
                            yield LLMStreamEvent(
                                type="delta",
                                text=content or "",
                                reasoning=reasoning_content or "",
                                model=model,
                            )
                        # 解析增量 tool_calls
                        tool_calls = delta.get("tool_calls")
                        if tool_calls and isinstance(tool_calls, list):
                            for tc_delta in tool_calls:
                                if not isinstance(tc_delta, dict):
                                    continue
                                idx = tc_delta.get("index", 0)
                                if idx not in accumulated_tool_calls:
                                    accumulated_tool_calls[idx] = {}
                                acc = accumulated_tool_calls[idx]
                                if "id" in tc_delta:
                                    acc["id"] = tc_delta["id"]
                                if "type" in tc_delta:
                                    acc["type"] = tc_delta["type"]
                                if "function" in tc_delta and isinstance(tc_delta["function"], dict):
                                    func = tc_delta["function"]
                                    if "function" not in acc:
                                        acc["function"] = {}
                                    if "name" in func:
                                        acc["function"]["name"] = func["name"]
                                    if "arguments" in func:
                                        acc["function"].setdefault("arguments", "")
                                        acc["function"]["arguments"] += func["arguments"]
                            finish_reason = choice.get("finish_reason")
                            if finish_reason == "tool_calls":
                                yield LLMStreamEvent(
                                    type="tool_calls",
                                    tool_calls=[
                                        {"id": v.get("id", ""), "type": v.get("type", "function"), "function": v.get("function", {})}
                                        for v in accumulated_tool_calls.values()
                                        if v.get("function", {}).get("name")
                                    ],
                                    model=model,
                                )
        yield LLMStreamEvent(type="done", usage=usage or {}, model=model)

    async def _mock_chat(self, messages: list[dict[str, str]], *, purpose: str) -> LLMResult:
        text = self._mock_text(messages, purpose)
        await asyncio.sleep(0.05)
        return LLMResult(
            text=text,
            model="mock-ark-compatible",
            usage={"input_tokens": 128, "output_tokens": max(10, len(text) // 3)},
            raw={"mock": True, "purpose": purpose},
        )

    async def _mock_stream(
        self, messages: list[dict[str, str]], *, purpose: str, tools: list[dict[str, Any]] | None = None
    ) -> AsyncIterator[LLMStreamEvent]:
        text = self._mock_text(messages, purpose)
        # 如果传入了 tools，模拟工具调用场景
        if tools and "file" in text.lower():
            yield LLMStreamEvent(type="delta", text="我来帮您处理文件请求。", model="mock-ark-compatible")
            await asyncio.sleep(0.05)
            yield LLMStreamEvent(
                type="tool_calls",
                tool_calls=[
                    {
                        "id": "call_mock_001",
                        "type": "function",
                        "function": {"name": "file.extract_text", "arguments": '{"file_id": "mock-file-id"}'},
                    }
                ],
                model="mock-ark-compatible",
            )
            yield LLMStreamEvent(
                type="usage",
                usage={"input_tokens": 128, "output_tokens": 20},
                model="mock-ark-compatible",
            )
            yield LLMStreamEvent(type="done", usage={}, model="mock-ark-compatible")
            return
        for token in text.split(" "):
            yield LLMStreamEvent(type="delta", text=token + " ", model="mock-ark-compatible")
            await asyncio.sleep(0.025)
        yield LLMStreamEvent(
            type="usage",
            usage={"input_tokens": 128, "output_tokens": max(10, len(text) // 3)},
            model="mock-ark-compatible",
        )
        yield LLMStreamEvent(type="done", usage={}, model="mock-ark-compatible")

    def _mock_text(self, messages: list[dict[str, str]], purpose: str) -> str:
        user_text = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        if purpose == "review":
            return (
                "[mock] Reviewer 审查通过：产物结构完整，包含可预览页面、清晰任务拆解、"
                "基本异常提示和部署入口。建议演示时强调 Mock/真实方舟可切换。"
            )
        if purpose == "summary":
            return f"[mock] 已压缩上下文，保留最近目标：{user_text[:100]}"
        return (
            "[mock] 主控 Agent 已理解任务："
            f"{user_text[:160]}。我会拆解为前端工作台、后端 API、数据模型、实时流、"
            "Reviewer 审查与部署预览几个并行子任务，并在完成后生成可编辑产物卡片。"
        )


ark_client = ArkClient()
