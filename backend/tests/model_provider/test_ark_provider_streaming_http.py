import pytest

from model_provider.core.interfaces import ChatMessage
from model_provider.providers import ark as ark_module


@pytest.mark.asyncio
async def test_chat_stream_yields_http_stream_chunks(monkeypatch):
    lines = [
        'data: {"choices":[{"delta":{"content":"Hel"},"finish_reason":null}]}',
        'data: {"choices":[{"delta":{"content":"lo"},"finish_reason":"stop"}]}',
        "data: [DONE]",
    ]
    requests = []

    class FakeResponse:
        status_code = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def aiter_lines(self):
            for line in lines:
                yield line

        async def aread(self):
            return b""

    class FakeClient:
        def __init__(self, *, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        def stream(self, method, url, json, headers):
            requests.append(
                {
                    "method": method,
                    "url": url,
                    "payload": json,
                    "headers": headers,
                }
            )
            return FakeResponse()

    monkeypatch.setattr(ark_module, "AsyncArk", lambda **_kwargs: object())
    monkeypatch.setattr(ark_module.httpx, "AsyncClient", FakeClient)

    provider = ark_module.ArkProvider(
        {
            "provider": "openai_compatible",
            "model": "test-model",
            "api_key": "test-key",
            "base_url": "http://upstream.test/v1",
        }
    )

    chunks = []
    async for chunk in provider.chat_stream(
        messages=[ChatMessage(role="user", content="hello")]
    ):
        chunks.append(chunk)

    assert [chunk.content for chunk in chunks if chunk.content] == ["Hel", "lo"]
    assert chunks[-1].finish_reason == "stop"
    assert requests[0]["method"] == "POST"
    assert requests[0]["url"] == "http://upstream.test/v1/chat/completions"
    assert requests[0]["payload"]["stream"] is True
    assert requests[0]["payload"]["stream_options"] == {"include_usage": True}


def test_stream_chunks_from_payload_preserves_tool_call_deltas():
    chunks = ark_module._stream_chunks_from_payload(
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call-1",
                                "type": "function",
                                "function": {
                                    "name": "lookup",
                                    "arguments": '{"query":',
                                },
                            }
                        ]
                    },
                    "finish_reason": "tool_calls",
                }
            ]
        }
    )

    assert chunks == [
        ark_module.StreamChunk(
            tool_call={
                "index": 0,
                "id": "call-1",
                "type": "function",
                "function": {"name": "lookup", "arguments": '{"query":'},
            },
            finish_reason="tool_calls",
        )
    ]


def test_build_payload_disables_ark_thinking_by_default(monkeypatch):
    monkeypatch.setattr(ark_module, "AsyncArk", lambda **_kwargs: object())
    provider = ark_module.ArkProvider(
        {
            "provider": "openai_compatible",
            "model": "test-model",
            "api_key": "test-key",
            "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        }
    )

    payload = provider._build_payload(
        [ChatMessage(role="user", content="hello")],
        system_prompt=None,
        tools=None,
        temperature=0.7,
        max_tokens=None,
    )

    assert payload["thinking"] == {"type": "disabled"}
