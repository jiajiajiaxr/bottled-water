from __future__ import annotations

import asyncio
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.base import Base
from app.core.errors import ValidationAppError
from db.models import Skill, User
from app.services.skills.adapters.legacy import legacy_skill_manifest
from app.services.skills.dependencies import check_skill_dependencies
from app.services.skills.manifest import validate_manifest
from app.services.skills.runtime import SkillRuntime
from app.services.skills.testing import run_manifest_tests


def test_manifest_validation_and_legacy_skill_defaults() -> None:
    skill = Skill(
        name="需求分析 Skill",
        description="拆解需求",
        content="提取目标和约束",
        prompt="你是需求分析 Skill。",
        version="1.2.0",
        tools=[{"type": "mcp", "server_id": "server-1", "name": "file.read"}],
    )

    manifest = legacy_skill_manifest(skill)

    assert manifest["name"] == "需求分析 Skill"
    assert manifest["version"] == "1.2.0"
    assert manifest["runtime"] == "prompt_skill"
    assert manifest["dependencies"]["mcp_servers"] == ["server-1"]
    assert manifest["entry"]["prompt"] == "你是需求分析 Skill。"


def test_manifest_rejects_unknown_runtime() -> None:
    with pytest.raises(ValidationAppError):
        validate_manifest({"name": "Bad Skill", "runtime": "python_tool"})


def test_dependency_check_reports_missing_mcp() -> None:
    db = _memory_session()
    user = User(email="u@example.com", username="u", password_hash="x", display_name="User")
    db.add(user)
    db.commit()

    report = check_skill_dependencies(
        db,
        {
            "name": "MCP Skill",
            "dependencies": {"mcp_servers": ["missing-server"], "tools": [], "skills": []},
        },
        user=user,
    )

    assert report["ok"] is False
    assert report["missing"]["mcp_servers"] == ["missing-server"]


def test_manifest_test_cases_run_through_skill_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _memory_session()
    user = User(email="tester@example.com", username="tester", password_hash="x", display_name="Tester")
    skill = Skill(
        owner_id=None,
        name="Release Skill",
        description="Create release notes",
        prompt="Return release notes.",
        config={"tests": [{"input": {"prompt": "ship it"}}]},
    )
    db.add_all([user, skill])
    db.commit()

    async def fake_run(
        self: SkillRuntime,
        db: Any,
        *,
        skill: Skill,
        user: User,
        payload: dict[str, Any] | str,
        conversation: Any = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "type": "skill",
            "skill_id": skill.id,
            "skill_name": skill.name,
            "run_id": "run-1",
            "status": "succeeded",
            "output": "ok",
            "model": "mock",
        }

    monkeypatch.setattr(SkillRuntime, "run", fake_run)

    report = asyncio.run(run_manifest_tests(db, skill=skill, user=user))

    assert report["status"] == "passed"
    assert report["total"] == 1
    assert skill.extra["last_test"]["run_id"] == "run-1"


def _memory_session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return session_factory()
