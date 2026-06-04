import json
import uuid
from typing import Any

from sqlalchemy import select

from app.core.database import SessionLocal
from db.models import SkillRun


def unwrap(body: dict[str, Any]) -> Any:
    return body.get("data", body)


def test_skill_crud_and_test_does_not_expose_secrets(
    client: Any,
    auth_headers: dict[str, str],
) -> None:
    created = client.post(
        "/api/v1/skills",
        json={
            "name": f"Acceptance Skill {uuid.uuid4().hex[:8]}",
            "description": "Validates skill CRUD",
            "category": "qa",
            "content": "Check the request and return a short report.",
            "prompt": "You are a QA skill.",
            "tags": ["acceptance"],
            "config": {"api_key": "super-secret-key", "nested": {"token": "hidden-token"}},
        },
        headers=auth_headers,
    )
    assert created.status_code == 200, created.text
    assert "super-secret-key" not in created.text
    assert "hidden-token" not in created.text
    skill = unwrap(created.json())
    skill_id = skill["id"]
    assert skill["config"]["api_key"] == "***"

    listed = client.get("/api/v1/skills?source=manual", headers=auth_headers)
    assert listed.status_code == 200, listed.text
    assert any(item["id"] == skill_id for item in unwrap(listed.json())["items"])

    updated = client.patch(
        f"/api/v1/skills/{skill_id}",
        json={"description": "Updated skill", "tags": ["acceptance", "updated"]},
        headers=auth_headers,
    )
    assert updated.status_code == 200, updated.text
    assert unwrap(updated.json())["description"] == "Updated skill"

    tested = client.post(
        f"/api/v1/skills/{skill_id}/test",
        json={"message": "Run a smoke test"},
        headers=auth_headers,
    )
    assert tested.status_code == 200, tested.text
    result = unwrap(tested.json())
    assert result["status"] == "passed"
    assert result["response"]
    assert result["run_id"]
    with SessionLocal() as db:
        run = db.scalar(select(SkillRun).where(SkillRun.id == result["run_id"]))
        assert run is not None
        assert run.skill_id == skill_id
        assert run.status == "succeeded"
    serialized_skill = json.dumps(result["skill"], ensure_ascii=False)
    assert "super-secret-key" not in serialized_skill
    assert "hidden-token" not in serialized_skill

    deleted = client.delete(f"/api/v1/skills/{skill_id}", headers=auth_headers)
    assert deleted.status_code == 200, deleted.text
    assert unwrap(deleted.json())["deleted"] is True


def test_import_mcp_tools_generates_skill_without_server_secrets(
    client: Any,
    auth_headers: dict[str, str],
) -> None:
    mcp = client.post(
        "/api/v1/mcp-servers",
        json={
            "name": f"Acceptance MCP {uuid.uuid4().hex[:8]}",
            "transport": "stdio",
            "command": "agenthub-mcp-filesystem",
            "env": {"OPENAI_API_KEY": "mcp-secret-key"},
            "headers": {"Authorization": "Bearer mcp-secret-token"},
            "tool_filter": ["file.read", "sandbox.run"],
        },
        headers=auth_headers,
    )
    assert mcp.status_code == 200, mcp.text
    server_id = unwrap(mcp.json())["id"]

    probed = client.post(f"/api/v1/mcp-servers/{server_id}/probe", headers=auth_headers)
    assert probed.status_code == 200, probed.text

    imported = client.post(
        "/api/v1/skills/import-mcp",
        json={
            "mcp_server_id": server_id,
            "tool_names": ["file.read"],
            "name": "Filesystem Read Skill",
            "config": {"token": "import-secret-token"},
        },
        headers=auth_headers,
    )
    assert imported.status_code == 200, imported.text
    assert "mcp-secret-key" not in imported.text
    assert "mcp-secret-token" not in imported.text
    assert "import-secret-token" not in imported.text
    skill = unwrap(imported.json())
    assert skill["source"] == "mcp"
    assert skill["tools"][0]["name"] == "file.read"
    assert skill["config"]["token"] == "***"


def test_ai_generate_skill_uses_adapter_with_mock_fallback(
    client: Any,
    auth_headers: dict[str, str],
) -> None:
    generated = client.post(
        "/api/v1/skills/generate",
        json={
            "name": "Release Notes Skill",
            "intent": "Generate concise release notes from a list of changes.",
            "requirements": "Group changes by feature, fix, and risk.",
            "tags": ["release"],
        },
        headers=auth_headers,
    )
    assert generated.status_code == 200, generated.text
    skill = unwrap(generated.json())
    assert skill["source"] == "ai"
    assert skill["name"] == "Release Notes Skill"
    assert "generation" in skill["config"]
    assert skill["config"]["generation"]["provider_status"]


def test_skill_api_test_runs_manifest_script_runtime(
    client: Any,
    auth_headers: dict[str, str],
) -> None:
    created = client.post(
        "/api/v1/skills",
        json={
            "name": f"API Script Skill {uuid.uuid4().hex[:8]}",
            "description": "Runs a script through SkillRuntime",
            "category": "automation",
        },
        headers=auth_headers,
    )
    assert created.status_code == 200, created.text
    skill = unwrap(created.json())

    updated = client.patch(
        f"/api/v1/skills/{skill['id']}",
        json={
            "config": {
                "manifest": {
                    "name": "API Script Skill",
                    "runtime": "script_skill",
                    "entry": {
                        "script": (
                            "import json\n"
                            f"path = 'skills/{skill['id']}/skill_input.json'\n"
                            "data = json.load(open(path, encoding='utf-8'))\n"
                            "print('api-script-ok:' + data.get('prompt', ''))\n"
                        )
                    },
                    "dependencies": {"tools": ["file.write", "sandbox.run"]},
                }
            }
        },
        headers=auth_headers,
    )
    assert updated.status_code == 200, updated.text

    tested = client.post(
        f"/api/v1/skills/{skill['id']}/test",
        json={"message": "hello"},
        headers=auth_headers,
    )

    assert tested.status_code == 200, tested.text
    result = unwrap(tested.json())
    assert result["status"] == "passed"
    assert result["runtime"] == "script_skill"
    assert "api-script-ok:hello" in result["response"]
    with SessionLocal() as db:
        run = db.scalar(select(SkillRun).where(SkillRun.id == result["run_id"]))
        assert run is not None
        assert run.runtime_type == "script_skill"
        assert run.status == "succeeded"
