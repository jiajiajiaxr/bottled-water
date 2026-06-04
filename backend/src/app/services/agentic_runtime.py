"""Deprecated compatibility shim for AgentHub agent tool loops.

New code should import from ``app.services.agents.async_tool_loop`` for the
AsyncSession-backed runtime adapter path, or from
``app.services.agents.tool_loop`` for the synchronous Function Call loop path.
This module intentionally contains no business logic.
"""

from app.services.agents.async_tool_loop import (  # noqa: F401
    build_tools_for_agent,
    execute_builtin_tool_action,
    execute_mcp_action,
    execute_skill,
    execute_tool_by_name,
    run_agentic_tool_loop,
    select_agent_mcp_action,
    select_agent_skills,
    select_mcp_action,
    select_skills,
)

__all__ = [
    "build_tools_for_agent",
    "execute_builtin_tool_action",
    "execute_mcp_action",
    "execute_skill",
    "execute_tool_by_name",
    "run_agentic_tool_loop",
    "select_agent_mcp_action",
    "select_agent_skills",
    "select_mcp_action",
    "select_skills",
]
