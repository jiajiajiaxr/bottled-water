from __future__ import annotations

import asyncio
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db.base import Base
from app.core.errors import ValidationAppError
from db.models import Skill, SkillRun, ToolDefinition, ToolInvocation, User
from app.services.skills.adapters.legacy import legacy_skill_manifest
from app.services.skills.dependencies import check_skill_dependencies
from app.services.skills.manifest import validate_manifest
from app.services.skills.runtime import SkillRuntime
from app.services.skills.testing import run_manifest_tests
from app.services.skills.versions import manifest_hash, set_skill_manifest, skill_version_history


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


def test_manifest_accepts_mcp_and_script_runtimes() -> None:
    assert validate_manifest({"name": "MCP Skill", "runtime": "mcp_skill"})["runtime"] == "mcp_skill"
    assert validate_manifest({"name": "Script Skill", "runtime": "script_skill"})["runtime"] == "script_skill"


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
    assert skill.extra["last_test"]["status"] == "passed"
    assert skill.extra["test_reports"][-1]["cases"][0]["run_id"] == "run-1"


def test_skill_manifest_versions_store_recoverable_snapshots() -> None:
    db = _memory_session()
    user = User(email="version@example.com", username="version", password_hash="x", display_name="Version User")
    skill = Skill(owner_id=None, name="Versioned Skill", description="old", prompt="old", version="1.0.0")
    db.add_all([user, skill])
    db.commit()

    first = set_skill_manifest(
        skill,
        {
            "name": "Versioned Skill",
            "version": "1.0.0",
            "runtime": "prompt_skill",
            "entry": {"prompt": "first"},
        },
        user=user,
    )
    second = set_skill_manifest(
        skill,
        {
            "name": "Versioned Skill",
            "version": "1.1.0",
            "runtime": "prompt_skill",
            "description": "updated",
            "entry": {"prompt": "second"},
            "tests": [{"name": "smoke", "input": {"prompt": "hello"}}],
        },
        user=user,
    )

    assert skill.extra["manifest_hash"] == manifest_hash(second)
    history = skill_version_history(skill)
    assert history
    assert history[-1]["summary"]["version"] == first["version"]
    assert history[-1]["manifest"]["entry"]["prompt"] == "first"
    assert "version" in history[-1]["changed_fields"]
    assert history[-1]["replaced_by"]["hash"] == skill.extra["manifest_hash"]


def test_manifest_test_reports_store_case_level_results(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _memory_session()
    user = User(email="suite@example.com", username="suite", password_hash="x", display_name="Suite User")
    skill = Skill(
        owner_id=None,
        name="Suite Skill",
        description="Run suite",
        prompt="Return output.",
        config={
            "tests": [
                {"name": "pass", "input": {"prompt": "ok"}, "expect_contains": "ok"},
                {"name": "fail", "input": {"prompt": "bad"}, "expect_contains": "missing"},
            ]
        },
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
            "run_id": f"run-{payload.get('prompt')}",
            "status": "succeeded",
            "output": f"output:{payload.get('prompt')}",
        }

    monkeypatch.setattr(SkillRuntime, "run", fake_run)

    report = asyncio.run(run_manifest_tests(db, skill=skill, user=user))

    assert report["status"] == "failed"
    assert report["passed"] == 1
    assert report["failed"] == 1
    assert report["cases"][0]["status"] == "passed"
    assert report["cases"][1]["assertion"]["checks"][0]["passed"] is False
    assert skill.extra["last_test"]["id"] == report["id"]
    assert skill.extra["test_reports"][-1]["manifest_hash"] == manifest_hash(legacy_skill_manifest(skill))


def test_dependency_check_resolves_database_tool_catalog() -> None:
    db = _memory_session()
    user = User(email="tools@example.com", username="tools", password_hash="x", display_name="Tools User")
    tool = ToolDefinition(
        owner_id=user.id,
        name="custom.echo",
        display_name="Echo",
        description="Echo tool",
        type="custom_python",
        status="active",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
    )
    db.add_all([user, tool])
    db.commit()

    report = check_skill_dependencies(
        db,
        {"name": "Tool Skill", "dependencies": {"tools": ["custom.echo"]}},
        user=user,
    )

    assert report["ok"] is True
    assert report["missing"]["tools"] == []
    assert report["resolved"]["tools"][0]["tool_id"] == tool.id


def test_script_skill_requires_explicit_tool_dependencies() -> None:
    db = _memory_session()
    user = User(email="script-owner@example.com", username="script-owner", password_hash="x", display_name="Owner")
    skill = Skill(
        owner_id=None,
        name="Unsafe Script Skill",
        description="Missing dependencies",
        config={
            "runtime": "script_skill",
            "manifest": {
                "name": "Unsafe Script Skill",
                "runtime": "script_skill",
                "entry": {"script": "print('blocked')"},
            },
        },
    )
    skill.extra = {"manifest": skill.config["manifest"]}
    db.add_all([user, skill])
    db.commit()

    result = asyncio.run(SkillRuntime().run(db, skill=skill, user=user, payload={"prompt": "run"}))

    assert result["status"] == "failed"
    assert "requires tool dependencies" in str(result["output"])
    run = db.query(SkillRun).filter(SkillRun.skill_id == skill.id).one()
    assert run.status == "failed"


def test_script_skill_runs_through_file_and_sandbox_tools() -> None:
    db = _memory_session()
    user = User(email="script@example.com", username="script", password_hash="x", display_name="Script User")
    skill = Skill(
        owner_id=user.id,
        name="Script Skill",
        description="Run a controlled script",
        config={},
    )
    db.add_all([user, skill])
    db.commit()
    skill.extra = {
        "manifest": {
            "name": "Script Skill",
            "runtime": "script_skill",
            "entry": {
                "script": (
                    "import json\n"
                    "data = json.load(open('skills/%s/skill_input.json', encoding='utf-8'))\n"
                    "print('script-ok:' + data.get('prompt', ''))\n"
                )
                % skill.id,
            },
            "dependencies": {"tools": ["file.write", "sandbox.run"]},
        }
    }
    db.commit()

    result = asyncio.run(SkillRuntime().run(db, skill=skill, user=user, payload={"prompt": "hello"}))

    assert result["status"] == "succeeded"
    assert result["output"] == "script-ok:hello"
    assert result["runtime"] == "script_skill"
    invocations = db.query(ToolInvocation).filter(ToolInvocation.owner_id == user.id).all()
    assert [item.tool_name for item in invocations] == ["file.write", "file.write", "sandbox.run"]
    assert invocations[-1].status == "succeeded"


def _memory_session():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return session_factory()
