from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from db.base import Base
from db.models import (
    Agent,
    Artifact,
    Conversation,
    ConversationParticipant,
    FileAsset,
    Message,
    ToolInvocation,
    User,
    Workspace,
)
from app.services.agents.direct import _run_direct_agent_without_function_calling
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
from app.services.chat.mentions import normalize_agent_mentions
from app.services.chat.message_prompt import runtime_prompt_for_message


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


def test_runtime_prompt_includes_uploaded_file_context() -> None:
    message = Message(
        conversation_id="conv",
        sender_type="user",
        sender_name="User",
        content={
            "text": "总结这个文件",
            "attachments": [
                {
                    "file_id": "file-1",
                    "filename": "report.pdf",
                    "content_type": "application/pdf",
                    "parse_status": "parsed",
                    "extracted_text": "核心结论：本季度交付稳定。",
                }
            ],
        },
    )

    prompt = runtime_prompt_for_message(message)

    assert "总结这个文件" in prompt
    assert "file_id=file-1" in prompt
    assert "核心结论：本季度交付稳定。" in prompt
    assert "不要说没有收到文件" in prompt


def test_runtime_prompt_includes_agent_mentions_for_routing() -> None:
    message = Message(
        conversation_id="conv",
        sender_type="user",
        sender_name="User",
        content={
            "text": "请发表观点",
            "agent_mentions": [
                {"agent_id": "agent-ocean", "agent_name": "OCEAN"},
            ],
        },
    )

    prompt = runtime_prompt_for_message(message)

    assert "@OCEAN" in prompt
    assert "agent_id=agent-ocean" in prompt
    assert "must be scheduled" in prompt
    assert "请发表观点" in prompt


def test_agent_mentions_are_limited_to_active_conversation_participants() -> None:
    db = _memory_session()
    user, conversation = _user_conversation(db)
    target = _agent(db, user, name="OCEAN")
    outsider = _agent(db, user, name="Outside Agent")
    db.add(
        ConversationParticipant(
            conversation_id=conversation.id,
            participant_type="agent",
            agent_id=target.id,
        )
    )
    db.commit()

    mentions = normalize_agent_mentions(
        db,
        conversation_id=conversation.id,
        mentions=[
            {"agent_id": target.id},
            {"agent_id": outsider.id},
            {"agent_id": "missing-agent"},
        ],
    )

    assert mentions == [{"agent_id": target.id, "agent_name": "OCEAN"}]


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


def test_default_capability_context_matches_full_tool_catalog() -> None:
    db = _memory_session()
    user, conversation = _user_conversation(db)
    agent = _agent(db, user)
    message = _message(conversation, user, "调用 Claude Code")
    db.add(message)
    db.commit()

    bundle = ContextBuilder(db).build_agent_messages(
        conversation=conversation,
        user_message=message,
        agent=agent,
        system_prompt="系统提示",
        prompt="调用 Claude Code",
        mode="direct",
    )

    names = {item["name"] for item in bundle.sections["workspace"]["authorized_tools"]}
    assert "external_agent.invoke" in names
    assert "external_agent.run_claude_code" not in names


def test_explicit_empty_capability_context_stays_empty() -> None:
    db = _memory_session()
    user, conversation = _user_conversation(db)
    agent = _agent(db, user)
    agent.config = {"tools": [], "capability_permissions_initialized": True}
    message = _message(conversation, user, "调用 Claude Code")
    db.add(message)
    db.commit()

    bundle = ContextBuilder(db).build_agent_messages(
        conversation=conversation,
        user_message=message,
        agent=agent,
        system_prompt="系统提示",
        prompt="调用 Claude Code",
        mode="direct",
    )

    assert bundle.sections["workspace"]["authorized_tools"] == []


def test_group_history_preserves_agent_speaker_names() -> None:
    db = _memory_session()
    user = _user(db)
    conversation = _group_conversation(db, user)
    frontend = _agent(
        db,
        user,
        name="Frontend Worker",
        agent_type="frontend",
        description="负责 React 页面和交互实现",
        tools=["file.read"],
    )
    backend = _agent(
        db,
        user,
        name="Backend Worker",
        agent_type="backend",
        description="负责 FastAPI 与数据库服务",
        tools=["api.test"],
    )
    db.add_all([
        _participant(conversation, frontend),
        _participant(conversation, backend),
        _message(conversation, user, "请两个 Worker 分别评估方案"),
        Message(
            conversation_id=conversation.id,
            sender_type="agent",
            sender_id=frontend.id,
            sender_name=frontend.name,
            content={"text": "我会实现前端工作台。"},
            status="completed",
        ),
        Message(
            conversation_id=conversation.id,
            sender_type="agent",
            sender_id=backend.id,
            sender_name=backend.name,
            content={"text": "我会补充后端 API。"},
            status="completed",
        ),
    ])
    current = _message(conversation, user, "Backend 继续")
    db.add(current)
    db.commit()

    bundle = ContextBuilder(db).build_agent_messages(
        conversation=conversation,
        user_message=current,
        agent=backend,
        system_prompt="系统提示",
        prompt="Backend 继续",
        mode="workflow-agent",
    )
    serialized = "\n".join(str(item["content"]) for item in bundle.messages)

    assert "[Agent: Frontend Worker | role=frontend" in serialized
    assert "[Agent: Backend Worker | role=backend" in serialized
    assert "[User: Context User]" in serialized
    assert "我会实现前端工作台。" in serialized
    assert "我会补充后端 API。" in serialized


def test_group_context_lists_members_and_warns_current_agent_not_to_impersonate() -> None:
    db = _memory_session()
    user = _user(db)
    conversation = _group_conversation(db, user)
    frontend = _agent(
        db,
        user,
        name="Frontend Worker",
        agent_type="frontend",
        description="负责 React 页面和交互实现",
        tools=["file.read"],
    )
    backend = _agent(
        db,
        user,
        name="Backend Worker",
        agent_type="backend",
        description="负责 FastAPI 与数据库服务",
        tools=["api.test"],
    )
    db.add_all([_participant(conversation, frontend), _participant(conversation, backend)])
    current = _message(conversation, user, "你们分工是什么")
    db.add(current)
    db.commit()

    bundle = ContextBuilder(db).build_agent_messages(
        conversation=conversation,
        user_message=current,
        agent=frontend,
        system_prompt="系统提示",
        prompt="你们分工是什么",
        mode="workflow-agent",
    )
    system_message = str(bundle.messages[0]["content"])

    assert "你是当前 Agent：Frontend Worker" in system_message
    assert "其他群聊成员是协作者；你可以引用他们的发言和分工，但不要冒充他们发言。" in system_message
    assert "Backend Worker" in system_message
    assert "role=backend" in system_message
    assert "api.test" in system_message
    assert bundle.sections["group"]["enabled"] is True


def test_group_context_lists_default_full_tools_for_unconfigured_agents() -> None:
    db = _memory_session()
    user = _user(db)
    conversation = _group_conversation(db, user)
    backend = _agent(
        db,
        user,
        name="Backend Worker",
        agent_type="backend",
        description="负责 FastAPI 与数据库服务",
        tools=None,
    )
    db.add(_participant(conversation, backend))
    current = _message(conversation, user, "生成一个示例前后端数据管理项目")
    db.add(current)
    db.commit()

    bundle = ContextBuilder(db).build_agent_messages(
        conversation=conversation,
        user_message=current,
        agent=backend,
        system_prompt="系统提示",
        prompt="生成一个示例前后端数据管理项目",
        mode="workflow-agent",
    )

    system_message = str(bundle.messages[0]["content"])
    assert "file.write" in system_message
    assert "sandbox.run" in system_message
    assert "external_agent.invoke" in system_message


def test_context_system_prompt_explains_sandbox_command_shape() -> None:
    db = _memory_session()
    user, conversation = _user_conversation(db)
    agent = _agent(db, user)
    message = _message(conversation, user, "生成一个项目并运行")
    db.add(message)
    db.commit()

    bundle = ContextBuilder(db).build_agent_messages(
        conversation=conversation,
        user_message=message,
        agent=agent,
        system_prompt="系统提示",
        prompt="生成一个项目并运行",
        mode="agent_runtime",
    )

    system_message = str(bundle.messages[0]["content"])
    assert "sandbox.run、terminal.start 的 command 只能是单条可执行命令" in system_message
    assert "workdir" in system_message
    assert "不能声称依赖已安装、服务已启动" in system_message


def test_context_builder_uses_blackboard_and_current_agent_private_context() -> None:
    db = _memory_session()
    user = _user(db)
    conversation = _group_conversation(db, user)
    frontend = _agent(
        db,
        user,
        name="Frontend Worker",
        agent_type="frontend",
        description="负责 React 页面实现",
        tools=["file.read"],
    )
    backend = _agent(
        db,
        user,
        name="Backend Worker",
        agent_type="backend",
        description="负责 FastAPI 服务实现",
        tools=["sandbox.run"],
    )
    conversation.extra = {
        "workspace_id": None,
        "blackboard": {
            "version": 4,
            "structured_summaries": [
                {"title": "Round 1", "content": "共享结论：先实现登录页，再补 API。"}
            ],
            "kv_state": {"last_topic": "登录页", "shared_decision": "前后端并行"},
            "raw_history": [
                {
                    "type": "agent_result",
                    "agent_id": str(frontend.id),
                    "content": "Frontend 已完成登录页草图。",
                },
                {
                    "type": "tool_result",
                    "agent_id": str(backend.id),
                    "content": {"tool": "sandbox.run", "stdout": "pytest passed"},
                },
            ],
        },
        "agent_contexts": {
            str(backend.id): [
                {"type": "task", "content": "Backend 私有计划：先设计登录 API。"},
                {"type": "tool_result", "content": {"stdout": "backend lint passed"}},
            ],
            str(frontend.id): [
                {"type": "thought", "content": "Frontend 私有草稿：不要泄露给 Backend。"}
            ],
        },
    }
    db.add_all([_participant(conversation, frontend), _participant(conversation, backend)])
    current = _message(conversation, user, "Backend 继续")
    db.add(current)
    db.commit()

    bundle = ContextBuilder(db).build_agent_messages(
        conversation=conversation,
        user_message=current,
        agent=backend,
        system_prompt="系统提示",
        prompt="Backend 继续",
        mode="workflow-agent",
    )
    serialized = "\n".join(str(item["content"]) for item in bundle.messages)

    assert "Blackboard 全局共享上下文" in serialized
    assert "共享结论：先实现登录页，再补 API。" in serialized
    assert "shared_decision" in serialized
    assert "Frontend 已完成登录页草图。" in serialized
    assert "当前 Agent 私有上下文" in serialized
    assert "Backend 私有计划：先设计登录 API。" in serialized
    assert "backend lint passed" in serialized
    assert "Frontend 私有草稿：不要泄露给 Backend。" not in serialized
    assert bundle.sections["runtime_context"]["blackboard"]["version"] == 4
    assert bundle.sections["runtime_context"]["agent_context"]["frame_count"] == 2


def test_single_chat_does_not_include_group_member_context() -> None:
    db = _memory_session()
    user, conversation = _user_conversation(db)
    agent = _agent(db, user, name="Daily Chat Agent", agent_type="chat")
    message = _message(conversation, user, "你好")
    db.add(message)
    db.commit()

    bundle = ContextBuilder(db).build_agent_messages(
        conversation=conversation,
        user_message=message,
        agent=agent,
        system_prompt="系统提示",
        prompt="你好",
        mode="direct",
    )
    serialized = "\n".join(str(item["content"]) for item in bundle.messages)

    assert "群聊成员清单" not in serialized
    assert "[User:" not in serialized
    assert bundle.sections["group"]["enabled"] is False


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
        yield LLMStreamEvent(
            type="delta",
            text="在常规十进制算术里，一加一的标准答案为2。当然二进制里 1+1=10。",
        )
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


@pytest.mark.asyncio
async def test_direct_agent_fallback_uses_role_history() -> None:
    db = _memory_session()
    user, conversation = _user_conversation(db)
    agent = _agent(db, user)
    db.add_all([
        _message(conversation, user, "一加一等于多少"),
        Message(
            conversation_id=conversation.id,
            sender_type="agent",
            sender_id=agent.id,
            sender_name=agent.name,
            content={"text": "一加一等于2。"},
            status="completed",
        ),
    ])
    current = _message(conversation, user, "再加2呢")
    db.add(current)
    db.commit()

    async def fake_stream(messages: list[dict[str, str]], **_kwargs: object):
        serialized = "\n".join(str(item.get("content")) for item in messages)
        assert [item["role"] for item in messages][-3:] == ["user", "assistant", "user"]
        assert "一加一等于多少" in serialized
        assert "一加一等于2" in serialized
        assert messages[-1]["content"] == "再加2呢"
        yield LLMStreamEvent(type="delta", text="4")
        yield LLMStreamEvent(type="done", usage={})

    with patch("app.services.agents.direct.run_agentic_tool_loop", new_callable=AsyncMock) as tool_loop:
        tool_loop.return_value = {}
        with patch("app.services.agents.direct._publish_tool_artifacts", new_callable=AsyncMock):
            with patch("app.services.agents.direct.queue_service.enqueue", new_callable=AsyncMock):
                with patch("app.services.agents.direct.event_bus.publish", new_callable=AsyncMock):
                    with patch("app.services.agents.direct.ark_client.stream_chat", fake_stream):
                        await _run_direct_agent_without_function_calling(
                            db,
                            conversation=conversation,
                            user_message=current,
                            agent=agent,
                            prompt="再加2呢",
                            channel=f"conversation:{conversation.id}",
                        )

    assistant = db.scalar(
        select(Message)
        .where(Message.conversation_id == conversation.id, Message.sender_type == "agent")
        .order_by(Message.created_at.desc())
    )
    assert assistant is not None
    assert assistant.content["text"] == "4"
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


def _agent(
    db: Session,
    user: User,
    *,
    tools: list[str] | None = None,
    name: str = "Context Agent",
    agent_type: str = "assistant",
    description: str = "用于上下文验收的智能体",
) -> Agent:
    config = {"tools": tools or []}
    if tools is not None:
        config["capability_permissions_initialized"] = True
    agent = Agent(
        owner_id=user.id,
        name=name,
        type=agent_type,
        description=description,
        config=config,
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


def _group_conversation(db: Session, user: User) -> Conversation:
    conversation = Conversation(
        id=f"group-{user.id}",
        creator_id=user.id,
        chat_type="group",
        title="Group Context",
        extra={"workspace_id": None},
    )
    db.add(conversation)
    db.commit()
    return conversation


def _participant(conversation: Conversation, agent: Agent) -> ConversationParticipant:
    return ConversationParticipant(
        conversation_id=conversation.id,
        participant_type="agent",
        agent_id=agent.id,
        role="member",
    )
