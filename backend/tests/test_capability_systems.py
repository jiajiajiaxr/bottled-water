from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.core.database import Base
from app.models import Agent, McpServer, Skill, ToolDefinition, ToolInvocation, User
from app.services.demo_cleanup import cleanup_acceptance_residue
from app.services.mcp.discovery import discover_server_tools, import_server_manifest, probe_server
from app.services.mcp.schema import validate_mcp_arguments
from app.services.mcp.transports import tool_allowed
from app.services.skills.context import activated_skill_context
from app.services.skills.package import parse_skill_package
from app.services.tools.executor import invoke_tool
from app.services.tools.catalog import sync_builtin_tool_definitions


def test_tool_invocation_records_builtin_run() -> None:
    db = _memory_session()
    user = _user()
    db.add(user)
    db.commit()

    result = invoke_tool(db, user, "api.test", {"path": "/api/v1/health"})
    invocation = db.scalar(select(ToolInvocation).where(ToolInvocation.id == result["invocation_id"]))

    assert result["result"]["status"] == "succeeded"
    assert invocation is not None
    assert invocation.tool_name == "api.test"
    assert invocation.status == "succeeded"


def test_builtin_tools_sync_to_database_catalog() -> None:
    db = _memory_session()

    sync_builtin_tool_definitions(db)
    tool = db.scalar(select(ToolDefinition).where(ToolDefinition.name == "api.test"))

    assert tool is not None
    assert tool.type == "builtin"
    assert tool.is_builtin is True
    assert tool.builtin_handler == "api.test"
    assert tool.owner_id is None


def test_cleanup_acceptance_residue_soft_deletes_catalog_noise() -> None:
    db = _memory_session()
    db.add_all(
        [
            McpServer(name="Acceptance HTTP MCP", transport="httpStream", url="http://127.0.0.1", enabled=True),
            ToolDefinition(name="custom_echo_acceptance", display_name="custom_echo_acceptance", type="custom_python"),
            Skill(name="Release Notes Skill", source="ai", status="active"),
            Skill(name="需求分析 Skill", source="system", status="active"),
        ]
    )
    db.commit()

    cleanup_acceptance_residue(db)

    assert db.scalar(select(McpServer).where(McpServer.name == "Acceptance HTTP MCP")).deleted_at is not None
    assert db.scalar(select(ToolDefinition).where(ToolDefinition.name == "custom_echo_acceptance")).status == "deleted"
    assert db.scalar(select(Skill).where(Skill.name == "Release Notes Skill")).status == "deleted"
    assert db.scalar(select(Skill).where(Skill.name == "需求分析 Skill")).status == "active"


def test_mcp_catalog_discovery_and_probe() -> None:
    server = McpServer(
        owner_id="user-1",
        name="Filesystem MCP",
        transport="stdio",
        command="agenthub-mcp-filesystem",
        tool_filter=["file.*"],
        enabled=True,
    )

    tools = discover_server_tools(server)
    probe_server(server)

    assert tools[0]["name"] == "file.*"
    assert tool_allowed(server, "file.read")
    assert server.health_status == "online"


def test_mcp_argument_schema_validation() -> None:
    server = McpServer(
        id="server-schema",
        owner_id="user-1",
        name="Schema MCP",
        transport="httpStream",
        url="http://127.0.0.1:8765",
        enabled=True,
        tools=[
            {
                "name": "echo.ping",
                "enabled": True,
                "input_schema": {
                    "type": "object",
                    "properties": {"input": {"type": "string"}},
                    "required": ["input"],
                },
            }
        ],
    )

    validate_mcp_arguments(server, "echo.ping", {"input": "hello"})


def test_import_server_manifest_from_json() -> None:
    manifest = import_server_manifest(
        "json",
        '{"name":"Local MCP","transport":"httpStream","url":"http://127.0.0.1:8765","tools":[{"name":"echo.ping"}]}',
    )

    assert manifest["name"] == "Local MCP"
    assert manifest["tools"][0]["name"] == "echo.ping"


def test_skill_package_parse_and_activation_context(tmp_path: Path) -> None:
    package_dir = tmp_path / "release-skill"
    (package_dir / "scripts").mkdir(parents=True)
    (package_dir / "references").mkdir()
    (package_dir / "SKILL.md").write_text("Use this skill to write release notes.", encoding="utf-8")
    (package_dir / "manifest.json").write_text(
        '{"name":"Release Notes","version":"1.0.1","dependencies":{"tools":["document.review"]}}',
        encoding="utf-8",
    )
    (package_dir / "scripts" / "format.py").write_text("result = arguments", encoding="utf-8")

    manifest = parse_skill_package(package_dir)
    db = _memory_session()
    user = _user()
    skill = Skill(
        id="skill-release",
        owner_id=user.id,
        name="Release Notes",
        description="Write release notes",
        prompt="Use this skill to write release notes.",
        extra={"manifest": manifest},
    )
    agent = Agent(
        owner_id=user.id,
        name="Writer",
        type="custom",
        description="Writer",
        capabilities=[],
        config={"skill_ids": [skill.id]},
    )
    db.add_all([user, skill, agent])
    db.commit()

    context = activated_skill_context(db, agent)

    assert manifest["metadata"]["scripts"] == ["scripts/format.py"]
    assert "Release Notes" in context
    assert f"skill.{skill.id}" in context


def _memory_session() -> Any:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return session_factory()


def _user() -> User:
    return User(
        id="user-1",
        email="capabilities@example.com",
        username="capabilities",
        password_hash="x",
        display_name="Capabilities",
    )
