from __future__ import annotations

from typing import Any

from app.models import Agent
from app.services.tools.permissions import normalize_tool_names

CAPABILITY_PERMISSIONS_INITIALIZED = "capability_permissions_initialized"


def has_explicit_capability_permissions(agent: Agent | None) -> bool:
    """Return true once a user has saved an Agent's capability selections.

    Older Agent rows did not distinguish "no tools selected" from "not yet
    configured". To keep the product default friendly, missing marker means the
    Agent receives the full capability catalog. Once the UI saves a selection,
    this marker is set and the stored lists become authoritative.
    """
    if agent is None:
        return False
    config = agent.config or {}
    return bool(config.get(CAPABILITY_PERMISSIONS_INITIALIZED))


def configured_tool_names(agent: Agent | None) -> list[str]:
    if agent is None:
        return []
    return list(normalize_tool_names((agent.config or {}).get("tools") or []))


def configured_skill_ids(agent: Agent | None) -> list[str]:
    if agent is None:
        return []
    return [str(item) for item in (agent.config or {}).get("skill_ids") or [] if item]


def configured_mcp_server_ids(agent: Agent | None) -> list[str]:
    if agent is None:
        return []
    return [str(item) for item in (agent.config or {}).get("mcp_server_ids") or [] if item]


def agent_uses_default_full_permissions(agent: Agent | None) -> bool:
    return agent is not None and not has_explicit_capability_permissions(agent)


def mark_capability_permissions_initialized(config: dict[str, Any] | None) -> dict[str, Any]:
    next_config = dict(config or {})
    next_config[CAPABILITY_PERMISSIONS_INITIALIZED] = True
    return next_config
