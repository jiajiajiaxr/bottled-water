"""
火山引擎 Ark 模型提供者测试

需要 .env 文件中的 ARK_API_KEY 和 ARK_ENDPOINT_ID。
"""

import asyncio
import os
import pytest

# 从项目根目录加载 .env
from dotenv import load_dotenv

# 加载环境变量（从项目根目录）
env_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env")
load_dotenv(env_path)

from model_provider import create_provider, ModelConfig, ChatMessage


# --- 辅助函数 ---

def safe_print(text: str, max_len: int = 80) -> str:
    """安全打印：过滤掉终端不支持的非 ASCII 字符（如 emoji）"""
    safe = text[:max_len].encode("ascii", "ignore").decode("ascii")
    return safe if safe else "<non-ascii content>"


# --- fixtures ---

@pytest.fixture
def api_key():
    key = os.environ.get("ARK_API_KEY")
    if not key:
        pytest.skip("ARK_API_KEY not found in environment")
    return key


@pytest.fixture
def endpoint_id():
    eid = os.environ.get("ARK_ENDPOINT_ID")
    if not eid:
        pytest.skip("ARK_ENDPOINT_ID not found in environment")
    return eid


@pytest.fixture
def provider(api_key, endpoint_id):
    """创建 ArkProvider 实例"""
    return create_provider(ModelConfig(
        provider="ark",
        model=endpoint_id,
        api_key=api_key,
    ))


# --- 基础测试 ---

@pytest.mark.asyncio
async def test_create_provider(api_key, endpoint_id):
    """测试工厂函数创建 Provider"""
    provider = create_provider(ModelConfig(
        provider="ark",
        model=endpoint_id,
        api_key=api_key,
    ))
    assert provider is not None
    assert provider.model == endpoint_id
    print(f"\n[OK] Provider created: model={provider.model}")


@pytest.mark.asyncio
async def test_chat_simple(provider):
    """测试非流式对话"""
    messages = [ChatMessage(role="user", content="你好，请用一句话介绍自己")]

    response = await provider.chat(messages=messages)

    assert response is not None
    assert response.content
    assert len(response.content) > 0
    assert response.model is not None

    print(f"\n[OK] Chat response: {safe_print(response.content)}...")
    print(f"[OK] Model: {response.model}")
    if response.usage:
        print(f"[OK] Usage: {response.usage}")


@pytest.mark.asyncio
async def test_chat_with_system_prompt(provider):
    """测试带 system prompt 的对话"""
    messages = [ChatMessage(role="user", content="1+1等于几？")]

    response = await provider.chat(
        messages=messages,
        system_prompt="你是一个幽默的数学家，回答要简短有趣。",
    )

    assert response is not None
    assert response.content
    print(f"\n[OK] With system prompt: {safe_print(response.content)}...")


@pytest.mark.asyncio
async def test_chat_stream(provider):
    """测试流式对话"""
    messages = [ChatMessage(role="user", content="讲一个简短的笑话")]

    chunks = []
    async for chunk in provider.chat_stream(messages=messages):
        chunks.append(chunk)
        if chunk.content:
            print(chunk.content, end="", flush=True)

    print()  # newline

    assert len(chunks) > 0
    # 至少有一个 chunk 有内容或 finish_reason
    has_content = any(c.content for c in chunks)
    has_finish = any(c.finish_reason for c in chunks)
    assert has_content or has_finish, "Stream should have content or finish_reason"

    full_content = "".join(c.content for c in chunks)
    assert len(full_content) > 0
    print(f"\n[OK] Stream total chars: {len(full_content)}")


@pytest.mark.asyncio
async def test_chat_temperature(provider):
    """测试不同 temperature 参数"""
    messages = [ChatMessage(role="user", content="说一个随机数字")]

    # temperature=0 应该更确定
    response_low = await provider.chat(messages=messages, temperature=0.0)
    response_high = await provider.chat(messages=messages, temperature=1.0)

    assert response_low.content
    assert response_high.content
    print(f"\n[OK] temp=0: {safe_print(response_low.content)}")
    print(f"[OK] temp=1: {safe_print(response_high.content)}")


# --- 性能/辅助测试 ---

@pytest.mark.asyncio
async def test_count_tokens(provider):
    """测试 Token 估算"""
    text = "Hello World"
    count = provider.count_tokens(text)
    assert count > 0
    print(f"\n[OK] Token count for '{text}': {count}")


# --- 运行入口（用于直接执行） ---

if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
