from __future__ import annotations

import json
from typing import Any

from app.models import Skill
from app.services.llm.ark import ark_client


async def run_prompt_skill(
    skill: Skill,
    manifest: dict[str, Any],
    runtime_input: dict[str, Any],
    *,
    purpose: str = "skill_execution",
) -> dict[str, Any]:
    response = await ark_client.chat(
        [
            {"role": "system", "content": system_prompt(skill, manifest)},
            {"role": "user", "content": json.dumps(runtime_input, ensure_ascii=False)},
        ],
        temperature=0.2,
        max_tokens=800,
        purpose=purpose,
    )
    return {
        "status": "succeeded",
        "output": response.text,
        "model": response.model,
        "usage": response.usage,
        "provider_status": getattr(response, "provider_status", "ok"),
        "runtime": manifest["runtime"],
    }


def system_prompt(skill: Skill, manifest: dict[str, Any]) -> str:
    entry = manifest.get("entry") if isinstance(manifest.get("entry"), dict) else {}
    return str(entry.get("prompt") or skill.prompt or skill.content or f"You are the AgentHub skill {skill.name}.")


def input_text(runtime_input: dict[str, Any]) -> str:
    for key in ("prompt", "input", "text", "query"):
        if runtime_input.get(key):
            return str(runtime_input[key])
    return json.dumps(runtime_input, ensure_ascii=False)

