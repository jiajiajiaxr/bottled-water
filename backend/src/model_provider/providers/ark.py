"""
火山引擎 Ark 适配器

使用 volcenginesdkarkruntime 的 AsyncArk 客户端。
不做 HTTP 封装，只做类型转换。
"""

from typing import AsyncIterator, List, Optional, Dict, Any

from volcenginesdkarkruntime import AsyncArk

from common.logger import get_logger
from ..core.interfaces import BaseModelProvider, ChatMessage, ChatResponse, StreamChunk

logger = get_logger(__name__)


class ArkProvider(BaseModelProvider):
    """火山引擎 Ark 实现

    使用 AsyncArk SDK，接口与 OpenAI 兼容。
    """

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.api_key = config["api_key"]
        self.base_url = config.get("base_url")

        # 初始化 AsyncArk 异步客户端
        client_kwargs = {"api_key": self.api_key}
        if self.base_url:
            client_kwargs["base_url"] = self.base_url

        self.client = AsyncArk(**client_kwargs)

    async def chat(
        self,
        messages: List[ChatMessage],
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict]] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> ChatResponse:
        payload = self._build_payload(messages, system_prompt, tools, temperature, max_tokens)

        logger.info("chat 调用开始", model=self.model, msg_count=len(messages), temperature=temperature)

        try:
            response = await self.client.chat.completions.create(**payload)
        except Exception as e:
            logger.error(f"chat 调用失败 model={self.model} error={str(e)}")
            raise

        choice = response.choices[0]
        message = choice.message

        # 提取 tool_calls
        tool_calls = None
        if hasattr(message, "tool_calls") and message.tool_calls:
            tool_calls = []
            for tc in message.tool_calls:
                tc_dict = {"id": tc.id, "type": tc.type}
                if hasattr(tc, "function"):
                    tc_dict["function"] = {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    }
                tool_calls.append(tc_dict)

        # 提取 usage
        usage = None
        if hasattr(response, "usage") and response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }
            logger.info("chat 调用完成", model=self.model, usage=usage)
        else:
            logger.info("chat 调用完成", model=self.model)

        return ChatResponse(
            content=message.content or "",
            tool_calls=tool_calls,
            usage=usage,
            model=response.model if hasattr(response, "model") else None,
        )

    async def chat_stream(
        self,
        messages: List[ChatMessage],
        system_prompt: Optional[str] = None,
        tools: Optional[List[Dict]] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
    ) -> AsyncIterator[StreamChunk]:
        payload = self._build_payload(messages, system_prompt, tools, temperature, max_tokens)
        payload["stream"] = True

        logger.info("chat_stream 调用开始", model=self.model, msg_count=len(messages))

        total_chars = 0
        try:
            stream = await self.client.chat.completions.create(**payload)
            async for chunk in stream:
                delta = chunk.choices[0].delta if chunk.choices else None
                if not delta:
                    continue

                tool_call = None
                if hasattr(delta, "tool_calls") and delta.tool_calls:
                    tc = delta.tool_calls[0]
                    tool_call = {
                        "id": tc.id,
                        "type": tc.type,
                    }
                    if hasattr(tc, "function"):
                        tool_call["function"] = {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        }

                content = delta.content or ""
                total_chars += len(content)

                yield StreamChunk(
                    content=content,
                    tool_call=tool_call,
                    finish_reason=chunk.choices[0].finish_reason if chunk.choices else None,
                )
        except Exception as e:
            logger.error(f"chat_stream 调用失败 model={self.model} error={str(e)}")
            raise

        logger.info("chat_stream 调用完成", model=self.model, total_chars=total_chars)

    def _build_payload(
        self,
        messages: List[ChatMessage],
        system_prompt: Optional[str],
        tools: Optional[List[Dict]],
        temperature: float,
        max_tokens: Optional[int],
    ) -> Dict[str, Any]:
        """构建 SDK 参数"""
        msgs = []
        if system_prompt:
            msgs.append({"role": "system", "content": system_prompt})
        for m in messages:
            msg = {"role": m.role, "content": m.content}
            if m.name:
                msg["name"] = m.name
            msgs.append(msg)

        payload = {
            "model": self.model,
            "messages": msgs,
            "temperature": temperature,
        }
        if tools:
            payload["tools"] = tools
        if max_tokens:
            payload["max_tokens"] = max_tokens
        return payload
