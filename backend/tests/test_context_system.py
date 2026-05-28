from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import Base
from app.models import Agent, Artifact, Conversation, FileAsset, Message, ToolInvocation, User, Workspace
from app.services.agents.function_loop import run_agent_function_call_loop
from app.services.ark import LLMStreamEvent
from app.services.context.builder import ContextBuilder
from app.services.context.memory import (
    attachment_context,
    load_conversation_memory,
    should_remember_workspace_fact,
    write_workspace_memory,
)
from app.services.context.state import conversation_state, update_conversation_state_after_turn
from app.services.context.variables import artifact_reference_scope, resolve_value


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
    current = _message(conversation, user, "当前问题")
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


def test_context_builder_orders_context_before_latest_input() -> None:
    db = _memory_session()
    user, conversation = _user_conversation(db)
    agent = _agent(db, user, tools=["sandbox.run"])
    message = _message(conversation, user, "使用资源")
    db.add_all([
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
    system_message = bundle.messages[0]["content"]
    latest_message = bundle.messages[-1]["content"]

    assert [item["role"] for item in bundle.messages] == ["system", "user"]
    assert "项目方案正文" in system_message
    assert "方案 PDF" in system_message
    assert "sandbox.run" in system_message
    assert "短期记忆：最近原文对话" not in system_message
    assert latest_message == "使用资源"


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
    db.add_all([
        _message(conversation, user, "你好"),
        Message(
            conversation_id=conversation.id,
            sender_type="agent",
            sender_id=agent.id,
            sender_name=agent.name,
            content={"text": "你好，我在。"},
            status="completed",
        ),
        Message(
            conversation_id=conversation.id,
            sender_type="agent",
            sender_id=agent.id,
            sender_name=agent.name,
            content={"text": "这条仍在生成中，不应作为完成回复使用。"},
            status="streaming",
        ),
    ])
    current = _message(conversation, user, "你能看到我刚才说了什么吗？")
    db.add(current)
    db.commit()

    async def fake_stream(messages: list[dict[str, str]], **_kwargs: object):
        serialized = "\n".join(str(item.get("content")) for item in messages)
        assert [item["role"] for item in messages] == ["system", "user", "assistant", "user"]
        assert "你好" in serialized
        assert "你好，我在。" in serialized
        assert "仍在生成中" not in serialized
        assert messages[1]["content"] == "你好"
        assert messages[2]["content"] == "你好，我在。"
        assert messages[-1]["content"] == "你能看到我刚才说了什么吗？"
        yield LLMStreamEvent(type="delta", text="能看到，你刚才说的是“你好”。")
        yield LLMStreamEvent(type="done", usage={})

    result = await _run_loop(db, conversation, current, agent, fake_stream)

    assert result.assistant is not None
    assert "你好" in result.assistant.content["text"]


@pytest.mark.asyncio
async def test_agent_loop_uses_role_history_and_state_for_math_followup() -> None:
    db = _memory_session()
    user, conversation = _user_conversation(db)
    agent = _agent(db, user)
    first = _message(conversation, user, "1+1等于几")
    db.add(first)
    db.commit()

    async def first_stream(messages: list[dict[str, str]], **_kwargs: object):
        assert messages[-1]["content"] == "1+1等于几"
        yield LLMStreamEvent(type="delta", text="2")
        yield LLMStreamEvent(type="done", usage={})

    first_result = await _run_loop(db, conversation, first, agent, first_stream)
    assert first_result.assistant is not None
    assert conversation_state(conversation)["last_math_result"] == 2

    followup = _message(conversation, user, "再加2呢")
    db.add(followup)
    db.commit()

    async def followup_stream(messages: list[dict[str, str]], **_kwargs: object):
        serialized = "\n".join(str(item.get("content")) for item in messages)
        assert [item["role"] for item in messages][-3:] == ["user", "assistant", "user"]
        assert "conversation_state" in serialized
        assert "last_math_result" in serialized
        assert "recent_turns_digest" in serialized
        assert "1+1等于几" in serialized
        assert "2" in serialized
        assert messages[-1]["content"] == "再加2呢"
        yield LLMStreamEvent(type="delta", text="4")
        yield LLMStreamEvent(type="done", usage={})

    result = await _run_loop(db, conversation, followup, agent, followup_stream)

    assert result.assistant is not None
    assert "4" in result.assistant.content["text"]
    assert conversation_state(conversation)["last_math_result"] == 4


def test_conversation_state_tracks_previous_topic_and_artifact_reference() -> None:
    db = _memory_session()
    user, conversation = _user_conversation(db)
    agent = _agent(db, user)
    user_message = _message(conversation, user, "生成一份红色主题的产品说明 PDF")
    assistant_message = Message(
        conversation_id=conversation.id,
        sender_type="agent",
        sender_id=agent.id,
        sender_name=agent.name,
        content={"text": "已生成产物。"},
        status="completed",
    )
    db.add_all([user_message, assistant_message])
    db.commit()

    update_conversation_state_after_turn(
        db,
        conversation,
        user_message=user_message,
        assistant_message=assistant_message,
        final_text="已生成产物。",
        tool_results=[{"result": {"artifact_id": "artifact-red-pdf"}}],
    )
    followup = _message(conversation, user, "把刚才那个改成蓝色")
    db.add(followup)
    db.commit()

    bundle = ContextBuilder(db).build_agent_messages(
        conversation=conversation,
        user_message=followup,
        agent=agent,
        system_prompt="系统提示",
        prompt="把刚才那个改成蓝色",
        mode="direct",
    )
    serialized = "\n".join(str(item["content"]) for item in bundle.messages)

    assert "last_topic" in serialized
    assert "last_artifact_id" in serialized
    assert "artifact-red-pdf" in serialized
    assert bundle.messages[-1]["content"] == "把刚才那个改成蓝色"


def test_old_project_background_summary_is_recovered() -> None:
    db = _memory_session()
    user, conversation = _user_conversation(db)
    agent = _agent(db, user)
    for index in range(18):
        text = "项目背景：北极星项目要做多 Agent 编排平台。" if index == 0 else f"大量历史细节 {index} " + ("内容" * 100)
        db.add(_message(conversation, user, text))
    current = _message(conversation, user, "继续推进项目")
    db.add(current)
    db.commit()

    bundle = ContextBuilder(db).build_agent_messages(
        conversation=conversation,
        user_message=current,
        agent=agent,
        system_prompt="系统提示",
        prompt="继续推进项目",
        mode="direct",
        token_budget=1200,
    )
    db.commit()
    reloaded = db.get(Conversation, conversation.id)
    serialized = "\n".join(str(item["content"]) for item in bundle.messages)

    assert "北极星项目" in reloaded.extra["context"]["summary"]
    assert "北极星项目" in serialized


@pytest.mark.asyncio
async def test_new_conversation_uses_only_workspace_memory_across_conversations() -> None:
    db = _memory_session()
    user = _user(db)
    workspace = Workspace(id="workspace-context", owner_id=user.id, name="Context Workspace", extra={})
    old_conversation = Conversation(
        id="conv-old",
        creator_id=user.id,
        chat_type="single",
        title="Old",
        extra={"workspace_id": workspace.id},
    )
    new_conversation = Conversation(
        id="conv-new",
        creator_id=user.id,
        chat_type="single",
        title="New",
        extra={"workspace_id": workspace.id},
    )
    agent = _agent(db, user)
    db.add_all([
        workspace,
        old_conversation,
        new_conversation,
        _message(old_conversation, user, "旧会话秘密：一次性口令 12345"),
    ])
    current = _message(new_conversation, user, "你知道项目背景吗？")
    db.add(current)
    db.commit()
    assert not should_remember_workspace_fact("项目背景：这只是普通聊天里提到的一句话。")
    assert should_remember_workspace_fact("请记住：项目背景是 bottled-water 长期多智能体平台。")

    first = ContextBuilder(db).build_agent_messages(
        conversation=new_conversation,
        user_message=current,
        agent=agent,
        system_prompt="系统提示",
        prompt="你知道项目背景吗？",
        mode="direct",
    )
    assert "一次性口令" not in "\n".join(str(item["content"]) for item in first.messages)

    write_workspace_memory(db, workspace, "项目背景：bottled-water 是长期多智能体平台项目。")
    second = ContextBuilder(db).build_agent_messages(
        conversation=new_conversation,
        user_message=current,
        agent=agent,
        system_prompt="系统提示",
        prompt="你知道项目背景吗？",
        mode="direct",
    )
    serialized = "\n".join(str(item["content"]) for item in second.messages)

    assert "bottled-water" in serialized
    assert "一次性口令" not in serialized


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
        _message(other, user, "旧会话秘密"),
    ])
    current = _message(conversation, user, "你知道旧会话秘密吗？")
    db.add(current)
    db.commit()

    async def fake_stream(messages: list[dict[str, str]], **_kwargs: object):
        serialized = "\n".join(str(item.get("content")) for item in messages[:-1])
        assert "旧会话秘密" not in serialized
        assert "不能读取其他未授权会话" in serialized
        yield LLMStreamEvent(type="delta", text="我不能读取其他未授权会话的内容。")
        yield LLMStreamEvent(type="done", usage={})

    result = await _run_loop(db, conversation, current, agent, fake_stream)

    assert result.assistant is not None
    assert "不能读取" in result.assistant.content["text"]


async def _run_loop(
    db: Session,
    conversation: Conversation,
    user_message: Message,
    agent: Agent,
    fake_stream: object,
):
    with patch("app.services.agents.function_loop.ark_client.stream_chat", fake_stream):
        with patch("app.services.agents.function_loop.event_bus.publish", new_callable=AsyncMock):
            return await run_agent_function_call_loop(
                db,
                conversation=conversation,
                user_message=user_message,
                agent=agent,
                prompt=str(user_message.content["text"]),
                channel=f"conversation:{conversation.id}",
                mode="context-test",
            )


def _memory_session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return session_factory()


def _user_conversation(db: Session) -> tuple[User, Conversation]:
    user = _user(db)
    conversation = Conversation(
        id="conv-context",
        creator_id=user.id,
        chat_type="single",
        title="Context",
        extra={"workspace_id": None},
    )
    db.add(conversation)
    db.commit()
    return user, conversation


def _user(db: Session) -> User:
    user = User(
        id="user-context",
        email="context@example.com",
        username="context",
        password_hash="x",
        display_name="Context User",
    )
    db.add(user)
    db.flush()
    return user


def _agent(db: Session, user: User, *, tools: list[str] | None = None) -> Agent:
    agent = Agent(
        owner_id=user.id,
        name="Context Agent",
        type="assistant",
        description="用于上下文验收的智能体",
        config={"tools": tools or []},
    )
    db.add(agent)
    db.commit()
    return agent


def _message(conversation: Conversation, user: User, text: str) -> Message:
    return Message(
        conversation_id=conversation.id,
        sender_type="user",
        sender_id=user.id,
        sender_name=user.display_name,
        content_type="text",
        content={"text": text},
        status="sent",
    )
