import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from db.base import Base
from db.models import Agent, Conversation, FileAsset, McpServer, McpToolInvocation, Message, Skill, ToolInvocation, User
from app.services.agents.function_loop import run_agent_function_call_loop


async def run_loop_with_mocked_edges(
    db: Any,
    conversation: Conversation,
    user_message: Message,
    agent: Agent,
    fake_stream: Any,
) -> Any:
    async def fake_skill_chat(*_args: Any, **_kwargs: Any) -> Any:
        return SimpleNamespace(text="Skill acceptance output: structured analysis complete", model="mock-skill", usage={}, provider_status="mock")

    async def fake_mcp_call(_server: McpServer, invocation: McpToolInvocation, _timeout_ms: int) -> dict[str, Any]:
        return {"result": {"text": f"MCP mock result for {invocation.arguments}"}}

    with patch("app.services.agents.function_loop.ark_client.stream_chat", fake_stream):
        with patch("app.services.skills.runners.prompt.ark_client.chat", fake_skill_chat):
            with patch("app.services.mcp.invocation.call_http_mcp", fake_mcp_call):
                with patch("app.services.agents.function_loop.event_bus.publish", new_callable=AsyncMock):
                    return await run_agent_function_call_loop(
                        db,
                        conversation=conversation,
                        user_message=user_message,
                        agent=agent,
                        prompt=str(user_message.content["text"]),
                        channel=f"conversation:{conversation.id}",
                        mode="acceptance-test",
                    )


def memory_session() -> Any:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)()


def conversation(db: Any, text: str) -> tuple[User, Conversation, Message]:
    user = User(email=f"{id(db)}@agent.test", username=f"user-{id(db)}", password_hash="x", display_name="验收用户")
    db.add(user)
    db.flush()
    session = Conversation(creator_id=user.id, chat_type="single", title="Agent 能力验收")
    db.add(session)
    db.flush()
    message = Message(
        conversation_id=session.id,
        sender_type="user",
        sender_id=user.id,
        sender_name=user.display_name,
        content_type="text",
        content={"text": text},
        status="sent",
        extra={},
    )
    db.add(message)
    db.commit()
    return user, session, message


def agent(
    db: Any,
    user: User,
    name: str,
    *,
    tools: list[str] | None = None,
    skill_ids: list[str] | None = None,
    mcp_server_ids: list[str] | None = None,
) -> Agent:
    row = Agent(
        owner_id=user.id,
        name=name,
        type="acceptance",
        description="Agent capability acceptance actor",
        config={"tools": tools or [], "skill_ids": skill_ids or [], "mcp_server_ids": mcp_server_ids or []},
        capabilities=[],
    )
    db.add(row)
    db.commit()
    return row


def file_asset(db: Any, root: Path, user: User, session: Conversation, filename: str, text: str) -> FileAsset:
    path = root / filename
    raw = text.encode("utf-8")
    path.write_bytes(raw)
    asset = FileAsset(
        owner_id=user.id,
        conversation_id=session.id,
        filename=filename,
        original_filename=filename,
        content_type="text/plain",
        size=len(raw),
        checksum=hashlib.sha256(raw).hexdigest(),
        storage_path=str(path),
        parse_status="pending",
        extracted_text="",
    )
    db.add(asset)
    db.commit()
    return asset


def skill(db: Any, user: User) -> Skill:
    row = Skill(
        owner_id=user.id,
        name="验收分析 Skill",
        description="用于对话级能力验收",
        status="active",
        content="输出结构化验收分析。",
        prompt="你是验收分析 Skill。",
        input_schema={"type": "object", "properties": {"prompt": {"type": "string"}}},
        output_schema={"type": "object", "properties": {"output": {"type": "string"}}},
    )
    db.add(row)
    db.commit()
    return row


def mcp_server(db: Any, user: User) -> McpServer:
    server = McpServer(
        owner_id=user.id,
        name="Mock MCP",
        transport="httpStream",
        url="http://mock-mcp.test/rpc",
        enabled=True,
        tools=[{"name": "echo.lookup", "enabled": True, "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}}}}],
        tool_filter=["echo.lookup"],
        timeout_ms=1000,
    )
    db.add(server)
    db.commit()
    return server


def tool_call(call_id: str, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)}}


def document_args(format_name: str) -> dict[str, Any]:
    return {
        "title": f"AgentHub {format_name.upper()} 验收报告",
        "content_model": {
            "title": f"AgentHub {format_name.upper()} 验收报告",
            "subtitle": "对话级能力验收",
            "template": "report",
            "sections": [{"title": "摘要", "blocks": [{"type": "paragraph", "text": "文件摘要已生成，产物可下载。"}]}],
        },
    }


def has_tool_result(messages: list[dict[str, Any]]) -> bool:
    return any(message.get("role") == "tool" for message in messages)


def assert_tools_exposed(kwargs: dict[str, Any], expected: list[str]) -> None:
    exposed = {item["function"]["name"] for item in kwargs.get("tools") or []}
    assert set(expected).issubset(exposed)


def tool_invocation_names(db: Any) -> list[str]:
    return [item.tool_name for item in db.scalars(select(ToolInvocation)).all()]
