from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import Base
from app.models import Agent, Artifact, Conversation, FileAsset, Message, ToolInvocation, User
from app.services.agents.function_loop import run_agent_function_call_loop
from app.services.context.builder import ContextBuilder
from app.services.context.memory import attachment_context, load_conversation_memory
from app.services.context.variables import artifact_reference_scope, resolve_value
from app.services.ark import LLMStreamEvent


def test_history_is_trimmed_and_summary_persisted() -> None:
    db = _memory_session()
    user, conversation = _user_conversation(db)
    for index in range(12):
        db.add(
            Message(
                conversation_id=conversation.id,
                sender_type="user",
                sender_id=user.id,
                sender_name="User",
                content={"text": f"历史消息 {index} " + ("内容" * 80)},
                status="sent",
            )
        )
    current = Message(
        conversation_id=conversation.id,
        sender_type="user",
        sender_id=user.id,
        sender_name="User",
        content={"text": "当前问题"},
        status="sent",
    )
    db.add(current)
    db.commit()

    memory = load_conversation_memory(db, conversation, current_message_id=current.id, token_budget=80)
    db.commit()
    reloaded = db.get(Conversation, conversation.id)

    assert len(memory.messages) < 12
    assert "历史消息" in memory.summary
    assert reloaded.extra["context"]["summary"] == memory.summary


def test_attachment_context_marks_text_and_images_honestly() -> None:
    message = Message(
        conversation_id="conv",
        sender_type="user",
        sender_name="User",
        content={
            "text": "请总结附件",
            "attachments": [
                {
                    "filename": "report.pdf",
                    "content_type": "application/pdf",
                    "extracted_text": "PDF 提取文本",
                },
                {"filename": "diagram.png", "content_type": "image/png", "extracted_text": ""},
            ],
        },
    )

    text = attachment_context(message)

    assert "PDF 提取文本" in text
    assert "未启用视觉解析" in text


def test_context_builder_includes_workspace_resources_and_runtime() -> None:
    db = _memory_session()
    user, conversation = _user_conversation(db)
    agent = Agent(id="agent-1", name="Writer", type="assistant", config={"max_context_tokens": 4000})
    message = Message(
        conversation_id=conversation.id,
        sender_type="user",
        sender_id=user.id,
        sender_name="User",
        content={"text": "使用资源"},
        status="sent",
    )
    db.add_all([
        agent,
        message,
        FileAsset(
            owner_id=user.id,
            conversation_id=conversation.id,
            filename="proposal.docx",
            original_filename="proposal.docx",
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            size=10,
            checksum="abc",
            storage_path="memory",
            parse_status="parsed",
            extracted_text="项目方案正文",
        ),
        Artifact(
            id="artifact-1",
            conversation_id=conversation.id,
            type="pdf",
            name="方案 PDF",
            status="ready",
            content={"format": "pdf"},
            mime_type="application/pdf",
        ),
        ToolInvocation(
            owner_id=user.id,
            conversation_id=conversation.id,
            tool_name="sandbox.run",
            tool_type="builtin",
            arguments={"command": "python --version"},
            result={"stdout": "Python 3.11"},
            status="succeeded",
        ),
    ])
    db.commit()

    bundle = ContextBuilder(db).build_agent_messages(
        conversation=conversation,
        user_message=message,
        agent=agent,
        system_prompt="系统提示",
        prompt="使用资源",
        mode="direct",
    )
    user_context = bundle.messages[-1]["content"]

    assert "项目方案正文" in user_context
    assert "方案 PDF" in user_context
    assert "sandbox.run" in user_context


def test_tool_result_message_uses_persisted_invocation() -> None:
    db = _memory_session()
    user, conversation = _user_conversation(db)
    invocation = ToolInvocation(
        owner_id=user.id,
        conversation_id=conversation.id,
        tool_name="api.test",
        tool_type="builtin",
        arguments={"path": "/health"},
        result={"status_code": 200, "assertion_passed": True},
        status="succeeded",
    )
    db.add(invocation)
    db.commit()

    message = ContextBuilder(db).tool_result_message(
        conversation=conversation,
        tool_call_id="call-1",
        result={"invocation_id": invocation.id},
    )

    assert message["role"] == "tool"
    assert "api.test" in message["content"]
    assert "assertion_passed" in message["content"]


def test_workflow_variable_scope_supports_upstream_and_artifact_refs() -> None:
    outputs = {
        "agent-frontend": {"text": "前端方案"},
        "artifact_node": {"id": "artifact-1", "title": "交付物", "export_url": "/export"},
    }
    scope = {
        "input": "原始输入",
        "nodes": outputs,
        "upstream": {"text": "上游汇总"},
        "artifact": artifact_reference_scope([outputs["artifact_node"]]),
    }

    resolved = resolve_value(
        {
            "input": "{{input}}",
            "node": "{{nodes.agent-frontend.text}}",
            "upstream": "{{upstream.text}}",
            "artifact": "{{artifact.artifact-1.title}}",
        },
        scope,
    )

    assert resolved == {
        "input": "原始输入",
        "node": "前端方案",
        "upstream": "上游汇总",
        "artifact": "交付物",
    }


@pytest.mark.asyncio
async def test_agent_loop_answers_from_current_conversation_history() -> None:
    db = _memory_session()
    user, conversation = _user_conversation(db)
    agent = _agent(db, user)
    previous = Message(
        conversation_id=conversation.id,
        sender_type="user",
        sender_id=user.id,
        sender_name="演示用户",
        content={"text": "你好"},
        status="sent",
    )
    completed = Message(
        conversation_id=conversation.id,
        sender_type="agent",
        sender_id=agent.id,
        sender_name=agent.name,
        content={"text": "你好，我在。"},
        status="completed",
    )
    streaming = Message(
        conversation_id=conversation.id,
        sender_type="agent",
        sender_id=agent.id,
        sender_name=agent.name,
        content={"text": "这条仍在生成中，不应作为完成回复使用。"},
        status="streaming",
    )
    current = Message(
        conversation_id=conversation.id,
        sender_type="user",
        sender_id=user.id,
        sender_name="演示用户",
        content={"text": "你能看到我刚才说了什么吗？"},
        status="sent",
    )
    db.add_all([previous, completed, streaming, current])
    db.commit()

    async def fake_stream(messages: list[dict[str, str]], **_kwargs: object):
        serialized = "\n".join(str(item.get("content")) for item in messages)
        assert "当前会话历史消息" in serialized
        assert "角色：用户" in serialized
        assert "时间：" in serialized
        assert "你好" in serialized
        assert "你好，我在。" in serialized
        assert "仍在生成中" not in serialized
        yield LLMStreamEvent(type="delta", text="能看到，你刚才说的是“你好”。")
        yield LLMStreamEvent(type="done", usage={})

    with patch("app.services.agents.function_loop.ark_client.stream_chat", fake_stream):
        with patch("app.services.agents.function_loop.event_bus.publish", new_callable=AsyncMock):
            result = await run_agent_function_call_loop(
                db,
                conversation=conversation,
                user_message=current,
                agent=agent,
                prompt="你能看到我刚才说了什么吗？",
                channel=f"conversation:{conversation.id}",
                mode="context-memory-test",
            )

    assert result.assistant is not None
    assert "你好" in result.assistant.content["text"]


@pytest.mark.asyncio
async def test_agent_loop_does_not_read_other_conversation_history() -> None:
    db = _memory_session()
    user, conversation = _user_conversation(db)
    other = Conversation(
        id="conv-other",
        creator_id=user.id,
        chat_type="single",
        title="Other",
        extra={},
    )
    agent = _agent(db, user)
    db.add_all([
        other,
        Message(
            conversation_id=other.id,
            sender_type="user",
            sender_id=user.id,
            sender_name="演示用户",
            content={"text": "旧会话秘密"},
            status="sent",
        ),
    ])
    current = Message(
        conversation_id=conversation.id,
        sender_type="user",
        sender_id=user.id,
        sender_name="演示用户",
        content={"text": "你知道旧会话秘密吗？"},
        status="sent",
    )
    db.add(current)
    db.commit()

    async def fake_stream(messages: list[dict[str, str]], **_kwargs: object):
        serialized = "\n".join(str(item.get("content")) for item in messages[:-1])
        assert "旧会话秘密" not in serialized
        assert "不能读取其他未授权会话" in serialized
        yield LLMStreamEvent(type="delta", text="我不能读取其他未授权会话的内容。")
        yield LLMStreamEvent(type="done", usage={})

    with patch("app.services.agents.function_loop.ark_client.stream_chat", fake_stream):
        with patch("app.services.agents.function_loop.event_bus.publish", new_callable=AsyncMock):
            result = await run_agent_function_call_loop(
                db,
                conversation=conversation,
                user_message=current,
                agent=agent,
                prompt="你知道旧会话秘密吗？",
                channel=f"conversation:{conversation.id}",
                mode="context-isolation-test",
            )

    assert result.assistant is not None
    assert "不能读取" in result.assistant.content["text"]


def _memory_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return session_factory()


def _user_conversation(db: Session) -> tuple[User, Conversation]:
    user = User(
        id="user-context",
        email="context@example.com",
        username="context",
        password_hash="x",
        display_name="Context User",
    )
    conversation = Conversation(
        id="conv-context",
        creator_id=user.id,
        chat_type="single",
        title="Context",
        extra={"workspace_id": None},
    )
    db.add_all([user, conversation])
    db.commit()
    return user, conversation


def _agent(db: Session, user: User) -> Agent:
    agent = Agent(
        owner_id=user.id,
        name="Context Agent",
        type="assistant",
        description="用于上下文验收的智能体",
        config={},
    )
    db.add(agent)
    db.commit()
    return agent
