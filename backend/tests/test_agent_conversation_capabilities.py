import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select

from agent_capability_support import (
    agent,
    assert_tools_exposed,
    conversation,
    document_args,
    file_asset,
    has_tool_result,
    mcp_server,
    memory_session,
    run_loop_with_mocked_edges,
    skill,
    tool_call,
    tool_invocation_names,
)
from db.models import Artifact, McpToolInvocation, Message, SkillRun, ToolInvocation
from app.services.ark import LLMStreamEvent
from app.services.tools.builtins.artifact.export import export_artifact
from app.services.llm.tool_calls import detect_artifact_tool


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("artifact_tool", "artifact_format", "extension"),
    [
        ("artifact.create_pdf", "pdf", ".pdf"),
        ("artifact.create_docx", "docx", ".docx"),
        ("artifact.create_html", "html", ".html"),
    ],
)
async def test_agent_extracts_file_summary_and_generates_document_artifact(
    tmp_path: Path,
    artifact_tool: str,
    artifact_format: str,
    extension: str,
) -> None:
    db = memory_session()
    user, session, user_message = conversation(db, "read the attachment and create a document")
    asset = file_asset(db, tmp_path, user, session, "brief.txt", "AgentHub supports Tool Skill MCP orchestration.")
    actor = agent(db, user, "Writing Agent", tools=["file.extract_text", "file.summarize", artifact_tool])

    async def fake_stream(messages: list[dict[str, Any]], **kwargs: Any) -> Any:
        assert_tools_exposed(kwargs, ["file.extract_text", "file.summarize", artifact_tool])
        if not has_tool_result(messages):
            yield LLMStreamEvent(
                type="tool_calls",
                tool_calls=[
                    tool_call("call-extract", "file.extract_text", {"file_id": asset.id}),
                    tool_call("call-summary", "file.summarize", {"file_id": asset.id, "max_chars": 300}),
                    tool_call("call-artifact", artifact_tool, document_args(artifact_format)),
                ],
            )
            yield LLMStreamEvent(type="done", usage={})
            return
        yield LLMStreamEvent(type="delta", text=f"summary and {artifact_format} artifact are ready")
        yield LLMStreamEvent(type="done", usage={})

    result = await run_loop_with_mocked_edges(db, session, user_message, actor, fake_stream)
    artifact = db.scalar(select(Artifact).where(Artifact.conversation_id == session.id))
    preview = db.scalar(select(Message).where(Message.content_type == "preview_card"))
    exported = export_artifact(artifact, artifact_format) if artifact else None

    assert tool_invocation_names(db)[:3] == ["file.extract_text", "file.summarize", artifact_tool]
    assert asset.extracted_text.startswith("AgentHub supports")
    assert artifact is not None
    assert artifact.content["format"] == artifact_format
    assert Path(artifact.content["source_file"]["storage_path"]).exists()
    assert preview is not None
    assert preview.content["artifact_id"] == artifact.id
    assert preview.content["format"] == artifact_format
    assert preview.content["filename"].endswith(extension)
    assert preview.content["media_type"] == artifact.content["media_type"]
    assert preview.content["export_url"].endswith(f"format={artifact_format}")
    assert exported is not None
    assert exported.filename.endswith(extension)
    assert len(exported.content) > 500
    assert any(item["tool_name"] == artifact_tool for item in result.tool_results)
    assert result.assistant and artifact_format in result.assistant.content["text"]


@pytest.mark.asyncio
async def test_explicit_pdf_preview_card_request_forces_real_artifact_when_model_only_streams_text() -> None:
    db = memory_session()
    user, session, user_message = conversation(db, "生成示例pdf预览卡片")
    actor = agent(db, user, "Daily Chat Agent", tools=["artifact.create_pdf"])
    calls: list[list[dict[str, Any]]] = []

    async def fake_stream(messages: list[dict[str, Any]], **kwargs: Any) -> Any:
        assert_tools_exposed(kwargs, ["artifact.create_pdf"])
        calls.append(messages)
        if len(calls) == 1:
            yield LLMStreamEvent(type="delta", text="📄 示例PDF预览卡片")
            yield LLMStreamEvent(type="done", usage={})
            return
        assert has_tool_result(messages)
        yield LLMStreamEvent(type="delta", text="真实 PDF 已生成，可以点击预览卡片查看。")
        yield LLMStreamEvent(type="done", usage={})

    result = await run_loop_with_mocked_edges(db, session, user_message, actor, fake_stream)
    artifact = db.scalar(select(Artifact).where(Artifact.conversation_id == session.id))
    preview = db.scalar(select(Message).where(Message.content_type == "preview_card"))

    assert detect_artifact_tool("生成示例pdf预览卡片") == "artifact.create_pdf"
    assert artifact is not None
    assert artifact.content["format"] == "pdf"
    assert preview is not None
    assert preview.content["artifact_id"] == artifact.id
    assert preview.content["format"] == "pdf"
    assert preview.content["export_url"].endswith("format=pdf")
    assert preview.content["media_type"] == "application/pdf"
    assert Path(artifact.content["source_file"]["storage_path"]).exists()
    assert result.assistant and "真实 PDF" in result.assistant.content["text"]


@pytest.mark.asyncio
async def test_agent_calls_bound_skill_and_feeds_result_to_final_reply() -> None:
    db = memory_session()
    user, session, user_message = conversation(db, "use the acceptance skill")
    target_skill = skill(db, user)
    actor = agent(db, user, "Skill Agent", skill_ids=[target_skill.id])

    async def fake_stream(messages: list[dict[str, Any]], **kwargs: Any) -> Any:
        assert_tools_exposed(kwargs, [f"skill.{target_skill.id}"])
        if not has_tool_result(messages):
            yield LLMStreamEvent(
                type="tool_calls",
                tool_calls=[tool_call("call-skill", f"skill.{target_skill.id}", {"prompt": "analyze AgentHub"})],
            )
            yield LLMStreamEvent(type="done", usage={})
            return
        assert "Skill acceptance output" in json.dumps(messages, ensure_ascii=False)
        yield LLMStreamEvent(type="delta", text="final answer uses the Skill acceptance output")
        yield LLMStreamEvent(type="done", usage={})

    result = await run_loop_with_mocked_edges(db, session, user_message, actor, fake_stream)
    run = db.scalar(select(SkillRun).where(SkillRun.skill_id == target_skill.id))

    assert run is not None
    assert run.status == "succeeded"
    assert result.tool_results[0]["tool_name"] == f"skill.{target_skill.id}"
    assert "Skill acceptance output" in str(result.tool_results[0]["result"]["output"])
    assert result.assistant and "final answer" in result.assistant.content["text"]


@pytest.mark.asyncio
async def test_agent_calls_bound_mcp_tool_and_records_invocation() -> None:
    db = memory_session()
    user, session, user_message = conversation(db, "query the external MCP tool")
    server = mcp_server(db, user)
    actor = agent(db, user, "MCP Agent", mcp_server_ids=[server.id])
    mcp_name = f"mcp.{server.id}.echo.lookup"

    async def fake_stream(messages: list[dict[str, Any]], **kwargs: Any) -> Any:
        assert_tools_exposed(kwargs, [mcp_name])
        if not has_tool_result(messages):
            yield LLMStreamEvent(type="tool_calls", tool_calls=[tool_call("call-mcp", mcp_name, {"query": "AgentHub"})])
            yield LLMStreamEvent(type="done", usage={})
            return
        yield LLMStreamEvent(type="delta", text="MCP returned AgentHub context")
        yield LLMStreamEvent(type="done", usage={})

    result = await run_loop_with_mocked_edges(db, session, user_message, actor, fake_stream)
    invocation = db.scalar(select(McpToolInvocation).where(McpToolInvocation.server_id == server.id))

    assert invocation is not None
    assert invocation.status == "succeeded"
    assert invocation.tool_name == "echo.lookup"
    assert result.tool_results[0]["tool_name"] == mcp_name
    assert "AgentHub" in json.dumps(invocation.result, ensure_ascii=False)


@pytest.mark.asyncio
async def test_agent_combines_tool_skill_and_mcp_across_multiple_rounds(tmp_path: Path) -> None:
    db = memory_session()
    user, session, user_message = conversation(db, "combine attachment, skill, and MCP")
    asset = file_asset(db, tmp_path, user, session, "combo.txt", "The combined chain needs ordered tool feedback.")
    target_skill = skill(db, user)
    server = mcp_server(db, user)
    mcp_name = f"mcp.{server.id}.echo.lookup"
    actor = agent(db, user, "Combo Agent", tools=["file.summarize"], skill_ids=[target_skill.id], mcp_server_ids=[server.id])
    call_order = ["file.summarize", f"skill.{target_skill.id}", mcp_name]

    async def fake_stream(messages: list[dict[str, Any]], **_kwargs: Any) -> Any:
        tool_result_count = sum(1 for message in messages if message.get("role") == "tool")
        if tool_result_count < len(call_order):
            name = call_order[tool_result_count]
            args = {"file_id": asset.id} if name == "file.summarize" else {"prompt": "combo"} if name.startswith("skill.") else {"query": "combo"}
            yield LLMStreamEvent(type="tool_calls", tool_calls=[tool_call(f"call-{tool_result_count}", name, args)])
            yield LLMStreamEvent(type="done", usage={})
            return
        yield LLMStreamEvent(type="delta", text="combined Tool Skill MCP analysis is complete")
        yield LLMStreamEvent(type="done", usage={})

    result = await run_loop_with_mocked_edges(db, session, user_message, actor, fake_stream)

    assert [item["tool_name"] for item in result.tool_results] == call_order
    assert db.scalar(select(ToolInvocation).where(ToolInvocation.tool_name == "file.summarize"))
    assert db.scalar(select(SkillRun).where(SkillRun.skill_id == target_skill.id))
    assert db.scalar(select(McpToolInvocation).where(McpToolInvocation.server_id == server.id))
    assert result.assistant and "combined" in result.assistant.content["text"]


@pytest.mark.asyncio
async def test_unbound_capabilities_are_rejected_without_running_them() -> None:
    db = memory_session()
    user, session, user_message = conversation(db, "try unbound capabilities")
    target_skill = skill(db, user)
    server = mcp_server(db, user)
    actor = agent(db, user, "No Permission Agent")
    names = ["api.test", f"skill.{target_skill.id}", f"mcp.{server.id}.echo.lookup"]

    async def fake_stream(messages: list[dict[str, Any]], **_kwargs: Any) -> Any:
        if not has_tool_result(messages):
            yield LLMStreamEvent(
                type="tool_calls",
                tool_calls=[tool_call(f"call-{idx}", name, {}) for idx, name in enumerate(names)],
            )
            yield LLMStreamEvent(type="done", usage={})
            return
        yield LLMStreamEvent(type="delta", text="current Agent has no permission for these capabilities")
        yield LLMStreamEvent(type="done", usage={})

    result = await run_loop_with_mocked_edges(db, session, user_message, actor, fake_stream)

    assert [item["status"] for item in result.tool_results] == ["failed", "failed", "failed"]
    assert db.scalar(select(ToolInvocation)) is None
    assert db.scalar(select(SkillRun)) is None
    assert db.scalar(select(McpToolInvocation)) is None
    assert result.assistant and "no permission" in result.assistant.content["text"]
