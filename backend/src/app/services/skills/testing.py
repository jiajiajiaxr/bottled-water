from __future__ import annotations

import json
import time
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models import Skill, User, utcnow
from app.services.serialization import redact_sensitive
from app.services.skills.adapters.legacy import legacy_skill_manifest
from app.services.skills.dependencies import check_skill_dependencies
from app.services.skills.runtime import SkillRuntime
from app.services.skills.versions import manifest_hash


async def run_skill_test(
    db: Session,
    *,
    skill: Skill,
    user: User,
    payload: dict[str, Any] | str,
    context: dict[str, Any] | None = None,
    case: dict[str, Any] | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    result = await SkillRuntime().run(
        db,
        skill=skill,
        user=user,
        payload=payload,
        context=context or {},
    )
    assertion = _evaluate_assertions(result, case or {})
    status = "passed" if _runtime_passed(result) and assertion["passed"] else "failed"
    duration_ms = int((time.perf_counter() - started) * 1000)
    report = {
        "status": status,
        "input_preview": str(payload)[:160],
        "provider_status": result.get("provider_status") or result.get("status"),
        "model": result.get("model"),
        "run_id": result.get("run_id"),
        "duration_ms": duration_ms,
        "assertion": assertion,
        "tested_at": utcnow().isoformat().replace("+00:00", "Z"),
    }
    skill.extra = {
        **(skill.extra or {}),
        "last_test": report,
    }
    db.flush()
    return {"status": status, "result": result, "assertion": assertion, "duration_ms": duration_ms}


async def run_manifest_tests(db: Session, *, skill: Skill, user: User) -> dict[str, Any]:
    manifest = legacy_skill_manifest(skill)
    tests = manifest.get("tests") or []
    suite_id = str(uuid4())
    started_at = utcnow().isoformat().replace("+00:00", "Z")
    dependency_report = check_skill_dependencies(db, manifest, user=user)
    cases: list[dict[str, Any]] = []
    for index, case in enumerate(tests):
        payload = case.get("input") if isinstance(case, dict) else {}
        report = await run_skill_test(
            db,
            skill=skill,
            user=user,
            payload=payload or {},
            case=case if isinstance(case, dict) else {},
        )
        cases.append(
            {
                "index": index,
                "name": str(case.get("name") or f"case-{index + 1}") if isinstance(case, dict) else f"case-{index + 1}",
                "status": report["status"],
                "run_id": report["result"].get("run_id"),
                "duration_ms": report["duration_ms"],
                "input": redact_sensitive(payload or {}),
                "assertion": report["assertion"],
                "output_preview": _preview(report["result"].get("output")),
                "provider_status": report["result"].get("provider_status") or report["result"].get("status"),
            }
        )
    status = "passed" if dependency_report["ok"] and all(item["status"] == "passed" for item in cases) else "failed"
    report = {
        "id": suite_id,
        "status": status,
        "total": len(cases),
        "passed": len([item for item in cases if item["status"] == "passed"]),
        "failed": len([item for item in cases if item["status"] == "failed"]),
        "manifest_hash": manifest_hash(manifest),
        "dependency_report": redact_sensitive(dependency_report),
        "started_at": started_at,
        "completed_at": utcnow().isoformat().replace("+00:00", "Z"),
        "cases": cases,
    }
    report["status"] = status
    metadata = dict(skill.extra or {})
    reports = metadata.get("test_reports") if isinstance(metadata.get("test_reports"), list) else []
    reports.append(report)
    metadata["test_reports"] = reports[-20:]
    metadata["last_test"] = {
        "id": suite_id,
        "status": status,
        "total": report["total"],
        "passed": report["passed"],
        "failed": report["failed"],
        "manifest_hash": report["manifest_hash"],
        "tested_at": report["completed_at"],
    }
    skill.extra = metadata
    db.flush()
    return report


def _runtime_passed(result: dict[str, Any]) -> bool:
    status = str(result.get("status") or "")
    return not (status.startswith("failed") or status.startswith("fallback"))


def _evaluate_assertions(result: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    expected = case.get("expected") if isinstance(case.get("expected"), dict) else {}
    expected_status = expected.get("status") or case.get("expected_status")
    output_text = _output_text(result.get("output"))
    checks: list[dict[str, Any]] = []
    if expected_status:
        checks.append(
            {
                "type": "status",
                "expected": expected_status,
                "actual": result.get("status"),
                "passed": result.get("status") == expected_status,
            }
        )
    contains = expected.get("contains") or case.get("expect_contains")
    if contains:
        needles = contains if isinstance(contains, list) else [contains]
        for needle in needles:
            checks.append(
                {
                    "type": "contains",
                    "expected": str(needle),
                    "passed": str(needle) in output_text,
                }
            )
    equals = expected.get("output") if "output" in expected else case.get("expected_output")
    if equals is not None:
        checks.append(
            {
                "type": "output_equals",
                "expected": redact_sensitive(equals),
                "actual": redact_sensitive(result.get("output")),
                "passed": result.get("output") == equals,
            }
        )
    return {"passed": all(item["passed"] for item in checks), "checks": checks}


def _output_text(output: Any) -> str:
    if isinstance(output, str):
        return output
    return json.dumps(output, ensure_ascii=False, sort_keys=True, default=str)


def _preview(value: Any) -> str:
    return _output_text(value)[:500]
