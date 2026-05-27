from __future__ import annotations

import time
from typing import Any

from sqlalchemy.orm import Session

from app.core.errors import ForbiddenError, ValidationAppError
from app.models import Conversation, Skill, SkillRun, User, utcnow
from app.services.skills.adapters.legacy import legacy_skill_manifest
from app.services.skills.catalog import ensure_skill_tables
from app.services.skills.dependencies import ensure_skill_dependencies
from app.services.skills.runners.agent import run_agent_skill
from app.services.skills.runners.mcp import legacy_mcp_refs, run_legacy_mcp
from app.services.skills.runners.prompt import input_text, run_prompt_skill
from app.services.tools.schema import validate_tool_arguments


class SkillRuntime:
    """Skill 包统一运行入口，只负责编排 prompt/runtime，不承载具体工具实现。"""

    async def run(
        self,
        db: Session,
        *,
        skill: Skill,
        user: User | None,
        payload: dict[str, Any] | str,
        conversation: Conversation | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ensure_skill_tables(db)
        manifest = legacy_skill_manifest(skill)
        runtime_input = _normalize_input(payload, context)
        validate_tool_arguments(manifest.get("input_schema"), runtime_input, tool_name=f"skill.{skill.id}")
        run = self._start_run(db, skill, user, conversation, manifest, runtime_input)
        started = time.perf_counter()
        try:
            ensure_skill_dependencies(db, manifest, user=user)
            result = await self._dispatch(db, skill, user, conversation, manifest, runtime_input)
            self._finish_run(run, "succeeded", result, started)
            return _tool_result(skill, manifest, run, "succeeded", result)
        except Exception as exc:
            fallback = await self._fallback(skill, manifest, runtime_input, exc)
            status = str(fallback.get("status") or "failed")
            self._finish_run(run, status, fallback, started, error=str(exc))
            return _tool_result(skill, manifest, run, status, fallback)

    def _start_run(
        self,
        db: Session,
        skill: Skill,
        user: User | None,
        conversation: Conversation | None,
        manifest: dict[str, Any],
        runtime_input: dict[str, Any],
    ) -> SkillRun:
        run = SkillRun(
            skill_id=skill.id,
            owner_id=user.id if user else skill.owner_id,
            conversation_id=conversation.id if conversation else None,
            runtime_type=str(manifest.get("runtime") or "prompt_skill"),
            status="running",
            input=runtime_input,
            output={},
            started_at=utcnow(),
            extra={"manifest": _manifest_summary(manifest)},
        )
        db.add(run)
        db.flush()
        return run

    async def _dispatch(
        self,
        db: Session,
        skill: Skill,
        user: User | None,
        conversation: Conversation | None,
        manifest: dict[str, Any],
        runtime_input: dict[str, Any],
    ) -> dict[str, Any]:
        if legacy_mcp_refs(manifest):
            return await run_legacy_mcp(db, skill, user, conversation, manifest, runtime_input)
        if manifest["runtime"] == "agent_skill":
            return await run_agent_skill(skill, manifest, runtime_input)
        return await run_prompt_skill(skill, manifest, runtime_input, purpose="skill_execution")

    def _finish_run(
        self,
        run: SkillRun,
        status: str,
        output: dict[str, Any],
        started: float,
        *,
        error: str | None = None,
    ) -> None:
        run.status = status
        run.output = output
        run.error_message = error
        run.duration_ms = int((time.perf_counter() - started) * 1000)
        run.completed_at = utcnow()

    async def _fallback(
        self,
        skill: Skill,
        manifest: dict[str, Any],
        runtime_input: dict[str, Any],
        exc: Exception,
    ) -> dict[str, Any]:
        prompt = input_text(runtime_input)
        if isinstance(exc, (ForbiddenError, ValidationAppError)):
            return {
                "status": "failed",
                "output": str(exc),
                "model": None,
                "provider_status": "dependency_or_permission_failed",
                "runtime": manifest["runtime"],
            }
        return {
            "status": f"fallback:{exc.__class__.__name__}",
            "output": f"[skill-fallback] {skill.name}: {prompt[:180]}",
            "model": "mock-skill-execution",
            "provider_status": f"mock_fallback:{exc.__class__.__name__}",
            "runtime": manifest["runtime"],
        }

def _normalize_input(payload: dict[str, Any] | str, context: dict[str, Any] | None) -> dict[str, Any]:
    if isinstance(payload, dict):
        runtime_input = dict(payload)
        if "prompt" not in runtime_input and "input" in runtime_input:
            runtime_input["prompt"] = str(runtime_input["input"])
    else:
        runtime_input = {"prompt": payload, "input": payload}
    runtime_input.setdefault("context", context or {})
    return runtime_input


def _tool_result(
    skill: Skill,
    manifest: dict[str, Any],
    run: SkillRun,
    status: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return {
        "type": payload.get("type") or "skill",
        "skill_id": skill.id,
        "skill_name": skill.name,
        "run_id": run.id,
        "runtime": manifest["runtime"],
        "manifest": _manifest_summary(manifest),
        "status": status,
        "output": payload.get("output"),
        "model": payload.get("model"),
        "usage": payload.get("usage"),
        "provider_status": payload.get("provider_status"),
        **({"invocation_id": payload["invocation_id"]} if payload.get("invocation_id") else {}),
    }

def _manifest_summary(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": manifest.get("name"),
        "version": manifest.get("version"),
        "runtime": manifest.get("runtime"),
    }
