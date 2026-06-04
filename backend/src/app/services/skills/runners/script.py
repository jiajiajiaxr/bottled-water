from __future__ import annotations

import json
from typing import Any

from app.core.errors import ValidationAppError
from app.models import Conversation, Skill, User
from app.services.tools.executor import invoke_tool_async


REQUIRED_SCRIPT_TOOLS = {"file.write", "sandbox.run"}


async def run_script_skill(
    db: Any,
    skill: Skill,
    user: User | None,
    conversation: Conversation | None,
    manifest: dict[str, Any],
    runtime_input: dict[str, Any],
) -> dict[str, Any]:
    """通过统一文件和沙箱工具执行受控 script Skill。"""

    if not user:
        raise ValidationAppError("script skill runner requires an authenticated user")
    declared_tools = set((manifest.get("dependencies") or {}).get("tools") or [])
    missing = sorted(REQUIRED_SCRIPT_TOOLS - declared_tools)
    if missing:
        raise ValidationAppError(f"script skill runner requires tool dependencies: {missing}")
    script = _script_source(manifest)
    base_args = _base_tool_args(skill, conversation, runtime_input)
    script_path = f"skills/{skill.id}/skill_script.py"
    input_path = f"skills/{skill.id}/skill_input.json"

    input_payload = json.dumps(runtime_input, ensure_ascii=False, indent=2)
    input_write = await invoke_tool_async(
        db,
        user,
        "file.write",
        {**base_args, "path": input_path, "content": input_payload},
    )
    script_write = await invoke_tool_async(
        db,
        user,
        "file.write",
        {**base_args, "path": script_path, "content": script},
    )
    sandbox = await invoke_tool_async(
        db,
        user,
        "sandbox.run",
        {
            **base_args,
            "command": f"python {script_path}",
            "timeout": int((manifest.get("entry") or {}).get("timeout_seconds") or 10),
        },
    )
    run_result = sandbox.get("result") or {}
    status = "succeeded" if run_result.get("status") == "succeeded" else "failed"
    output = str(run_result.get("stdout") or run_result.get("stderr") or "").strip()
    return {
        "status": status,
        "output": output,
        "runtime": manifest["runtime"],
        "type": "skill_script",
        "invocations": {
            "input_write": input_write.get("invocation_id"),
            "script_write": script_write.get("invocation_id"),
            "sandbox_run": sandbox.get("invocation_id"),
        },
        "stdout": run_result.get("stdout"),
        "stderr": run_result.get("stderr"),
        "exit_code": run_result.get("exit_code"),
        "duration_ms": run_result.get("duration_ms"),
        "script_path": script_path,
        "input_path": input_path,
    }


def _script_source(manifest: dict[str, Any]) -> str:
    entry = manifest.get("entry") if isinstance(manifest.get("entry"), dict) else {}
    language = str(entry.get("language") or "python").lower()
    if language not in {"python", "py"}:
        raise ValidationAppError("script skill runner currently supports python only")
    script = str(entry.get("script") or entry.get("code") or "").strip()
    if not script:
        raise ValidationAppError("script skill runner requires entry.script")
    return script


def _base_tool_args(
    skill: Skill,
    conversation: Conversation | None,
    runtime_input: dict[str, Any],
) -> dict[str, Any]:
    workspace_id = str(runtime_input.get("workspace_id") or skill.workspace_id or "")
    return {
        "workspace_id": workspace_id or None,
        "conversation_id": conversation.id if conversation else runtime_input.get("conversation_id"),
        "agent_id": runtime_input.get("agent_id"),
        "task_id": runtime_input.get("task_id") or f"skill-{skill.id}",
    }
