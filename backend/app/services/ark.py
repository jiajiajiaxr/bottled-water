from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Literal

import httpx

from app.core.config import Settings, get_settings


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
    type: Literal["delta", "usage", "done", "error"]
    text: str = ""
    usage: dict[str, Any] | None = None
    error: str | None = None
    model: str | None = None


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
    ) -> AsyncIterator[LLMStreamEvent]:
        if self.settings.use_mock_llm:
            async for item in self._mock_stream(messages, purpose=purpose):
                yield item
            return
        errors: list[dict[str, Any]] = []
        for model in self.settings.model_candidates:
            try:
                async for item in self._stream_model(
                    model,
                    {
                        "model": model,
                        "messages": messages,
                        "stream": True,
                        "stream_options": {"include_usage": True},
                        "max_tokens": max_tokens,
                        "temperature": temperature,
                    },
                ):
                    yield item
                return
            except Exception as exc:
                errors.append({"model": model, "error": str(exc)})
        yield LLMStreamEvent(type="error", error=json.dumps(errors, ensure_ascii=False))

    async def _post_json(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        if not self.settings.ark_api_key:
            raise ArkProviderError("缺少 ARK_API_KEY")
        async with httpx.AsyncClient(timeout=self.settings.ark_timeout_seconds) as client:
            response = await client.post(
                f"{self.base_url}{path}",
                json=body,
                headers={
                    "Authorization": f"Bearer {self.settings.ark_api_key}",
                    "Content-Type": "application/json",
                },
            )
        try:
            data = response.json()
        except ValueError:
            data = {"text": response.text}
        if response.status_code < 200 or response.status_code >= 300:
            raise ArkProviderError(json.dumps({"status": response.status_code, "error": data}))
        return data

    async def _stream_model(
        self, model: str, body: dict[str, Any]
    ) -> AsyncIterator[LLMStreamEvent]:
        if not self.settings.ark_api_key:
            raise ArkProviderError("缺少 ARK_API_KEY")
        usage: dict[str, Any] | None = None
        timeout = httpx.Timeout(self.settings.ark_stream_timeout_seconds)
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                json=body,
                headers={
                    "Authorization": f"Bearer {self.settings.ark_api_key}",
                    "Content-Type": "application/json",
                },
            ) as response:
                if response.status_code < 200 or response.status_code >= 300:
                    text = await response.aread()
                    raise ArkProviderError(
                        json.dumps(
                            {"status": response.status_code, "error": text.decode("utf-8", "replace")}
                        )
                    )
                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data_text = line.removeprefix("data:").strip()
                    if data_text == "[DONE]":
                        break
                    data = json.loads(data_text)
                    if data.get("usage"):
                        usage = data["usage"]
                        yield LLMStreamEvent(type="usage", usage=usage, model=model)
                    for choice in data.get("choices") or []:
                        delta = choice.get("delta") or {}
                        content = delta.get("content")
                        if content:
                            yield LLMStreamEvent(type="delta", text=content, model=model)
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
        self, messages: list[dict[str, str]], *, purpose: str
    ) -> AsyncIterator[LLMStreamEvent]:
        text = self._mock_text(messages, purpose)
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

