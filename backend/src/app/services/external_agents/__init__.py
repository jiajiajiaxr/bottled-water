"""External Coding Agent adapters.

Codex and Claude Code are modeled as long-running external coding agents.
They are exposed to AgentHub through adapters, then mapped into builtin tools.
"""

from app.services.external_agents.registry import get_external_agent_adapter, list_external_agent_adapters

__all__ = ["get_external_agent_adapter", "list_external_agent_adapters"]
