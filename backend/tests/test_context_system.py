from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import Base
from app.models import Agent, Artifact, Conversation, FileAsset, Message, ToolInvocation, User
from app.services.context.builder import ContextBuilder
from app.services.context.memory import attachment_context, load_conversation_memory
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
