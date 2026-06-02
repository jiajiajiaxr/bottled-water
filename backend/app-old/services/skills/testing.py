from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import Skill, User, utcnow
from app.services.skills.adapters.legacy import legacy_skill_manifest
from app.services.skills.runtime import SkillRuntime


async def run_skill_test(
    db: Session,
    *,
    skill: Skill,
    user: User,
    payload: dict[str, Any] | str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = await SkillRuntime().run(
        db,
        skill=skill,
        user=user,
        payload=payload,
        context=context or {},
    )
    status = "passed" if not str(result.get("status", "")).startswith("failed") else "failed"
    skill.extra = {
        **(skill.extra or {}),
        "last_test": {
            "status": status,
            "input_preview": str(payload)[:160],
            "provider_status": result.get("provider_status") or result.get("status"),
            "model": result.get("model"),
            "run_id": result.get("run_id"),
            "tested_at": utcnow().isoformat().replace("+00:00", "Z"),
        },
    }
    db.flush()
    return {"status": status, "result": result}


async def run_manifest_tests(db: Session, *, skill: Skill, user: User) -> dict[str, Any]:
    manifest = legacy_skill_manifest(skill)
    tests = manifest.get("tests") or []
    cases: list[dict[str, Any]] = []
    for index, case in enumerate(tests):
        payload = case.get("input") if isinstance(case, dict) else {}
        report = await run_skill_test(db, skill=skill, user=user, payload=payload or {})
        cases.append({"index": index, **report})
    return {
        "status": "passed" if all(item["status"] == "passed" for item in cases) else "failed",
        "total": len(cases),
        "cases": cases,
    }
