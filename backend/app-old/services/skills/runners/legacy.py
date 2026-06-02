"""Deprecated compatibility shim; use app.services.skills.runners.prompt/mcp."""

from app.services.skills.runners.agent import run_agent_skill
from app.services.skills.runners.mcp import legacy_mcp_refs, mcp_arguments, run_legacy_mcp
from app.services.skills.runners.prompt import input_text, run_prompt_skill, system_prompt

run_llm_skill = run_prompt_skill

__all__ = [
    "input_text",
    "legacy_mcp_refs",
    "mcp_arguments",
    "run_agent_skill",
    "run_legacy_mcp",
    "run_llm_skill",
    "run_prompt_skill",
    "system_prompt",
]
