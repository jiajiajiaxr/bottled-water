from __future__ import annotations

from app.core.errors import NotFoundError
from app.services.external_agents.adapters.claude_code import ClaudeCodeAdapter
from app.services.external_agents.adapters.codex import CodexAdapter
from app.services.external_agents.base import ExternalAgentAdapter


_ADAPTERS: dict[str, ExternalAgentAdapter] = {
    "codex": CodexAdapter(),
    "claude_code": ClaudeCodeAdapter(),
}


def list_external_agent_adapters() -> list[ExternalAgentAdapter]:
    return list(_ADAPTERS.values())


def get_external_agent_adapter(provider: str) -> ExternalAgentAdapter:
    key = provider.strip().lower().replace("-", "_")
    adapter = _ADAPTERS.get(key)
    if not adapter:
        raise NotFoundError("外部 Coding Agent 不存在")
    return adapter
