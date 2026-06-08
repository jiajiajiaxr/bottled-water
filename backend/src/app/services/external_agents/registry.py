from __future__ import annotations

from app.core.errors import NotFoundError
from app.services.external_agents.adapters.claude_code import ClaudeCodeAdapter
from app.services.external_agents.adapters.codex import CodexAdapter
from app.services.external_agents.adapters.opencode import OpenCodeAdapter
from app.services.external_agents.base import ExternalAgentAdapter


_ADAPTERS: dict[str, ExternalAgentAdapter] = {
    "codex": CodexAdapter(),
    "claude_code": ClaudeCodeAdapter(),
    "opencode": OpenCodeAdapter(),
}

_PROVIDER_ALIASES: dict[str, str] = {
    "claude": "claude_code",
    "claudecode": "claude_code",
    "claude_code_cli": "claude_code",
    "open_code": "opencode",
    "open_code_cli": "opencode",
    "opencode_cli": "opencode",
}


def list_external_agent_adapters() -> list[ExternalAgentAdapter]:
    return list(_ADAPTERS.values())


def register_external_agent_adapter(adapter: ExternalAgentAdapter) -> None:
    _ADAPTERS[_normalize_provider(adapter.name)] = adapter


def get_external_agent_adapter(provider: str) -> ExternalAgentAdapter:
    key = _normalize_provider(provider)
    adapter = _ADAPTERS.get(key)
    if not adapter:
        raise NotFoundError("外部 Coding Agent 不存在")
    return adapter


def _normalize_provider(provider: str) -> str:
    key = str(provider or "").strip().lower().replace("-", "_")
    return _PROVIDER_ALIASES.get(key, key)
