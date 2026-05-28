from __future__ import annotations

from typing import Any

from app.models import Skill
from app.services.skills.runners.prompt import run_prompt_skill


async def run_agent_skill(
    skill: Skill,
    manifest: dict[str, Any],
    runtime_input: dict[str, Any],
) -> dict[str, Any]:
    return await run_prompt_skill(
        skill,
        manifest,
        runtime_input,
        purpose="agent_skill_execution",
    )
