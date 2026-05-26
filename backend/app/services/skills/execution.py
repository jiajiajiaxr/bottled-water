from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.models import Conversation, McpServer, Skill, User
from app.services.ark import ark_client
from app.services.mcp_runtime import invoke_mcp_tool_recorded


async def run_llm_skill(
    skill: Skill,
    manifest: dict[str, Any],
    runtime_input: dict[str, Any],
    *,
    purpose: str,
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


async def run_legacy_mcp(
    db: Session,
    skill: Skill,
    user: User | None,
    conversation: Conversation | None,
    manifest: dict[str, Any],
    runtime_input: dict[str, Any],
) -> dict[str, Any]:
    ref = legacy_mcp_refs(manifest)[0]
    server = db.get(McpServer, str(ref["server_id"]))
    if not server:
        return {"status": "failed", "output": "MCP server not found", "runtime": manifest["runtime"]}
    invocation = await invoke_mcp_tool_recorded(
        db,
        server=server,
        tool_name_value=str(ref["name"]),
        arguments=mcp_arguments(runtime_input, str(ref["name"])),
        user=user,
        conversation_id=conversation.id if conversation else None,
        timeout_ms=min(server.timeout_ms or 30000, 5000),
    )
    return {
        "status": invocation["status"],
        "output": invocation.get("result") or invocation.get("error_message"),
        "invocation_id": invocation["id"],
        "runtime": manifest["runtime"],
        "type": "skill_mcp",
    }


def system_prompt(skill: Skill, manifest: dict[str, Any]) -> str:
    entry = manifest.get("entry") if isinstance(manifest.get("entry"), dict) else {}
    return str(entry.get("prompt") or skill.prompt or skill.content or f"You are the AgentHub skill {skill.name}.")


def input_text(runtime_input: dict[str, Any]) -> str:
    for key in ("prompt", "input", "text", "query"):
        if runtime_input.get(key):
            return str(runtime_input[key])
    return json.dumps(runtime_input, ensure_ascii=False)


def legacy_mcp_refs(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    entry = manifest.get("entry") if isinstance(manifest.get("entry"), dict) else {}
    refs = entry.get("legacy_tool_refs") if isinstance(entry.get("legacy_tool_refs"), list) else []
    return [
        item
        for item in refs
        if isinstance(item, dict) and item.get("type") == "mcp" and item.get("server_id") and item.get("name")
    ]


def mcp_arguments(runtime_input: dict[str, Any], name: str) -> dict[str, Any]:
    prompt = input_text(runtime_input)
    args = {"input": prompt, "prompt": prompt}
    if name.startswith("file.") or "read" in name:
        args.setdefault("path", runtime_input.get("path") or ".")
    if "sandbox" in name or "run" in name:
        args.setdefault("command", runtime_input.get("command") or "echo AgentHub MCP sandbox smoke")
    if "search" in name or "retrieve" in name:
        args.setdefault("query", prompt)
    return args
