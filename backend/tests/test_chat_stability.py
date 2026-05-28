from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import Base
from app.models import Agent, Conversation, Message, Task, User, WorkflowRun
from app.services.agents.function_loop import run_agent_function_call_loop
from app.services.agents.function_types import AgentFunctionLoopResult
from app.services.ark import LLMStreamEvent
from app.services.chat.artifacts import _publish_tool_artifacts
from app.services.chat.finalizer import fail_generation
from app.services.chat.orchestrator import _complete_independent_group
from app.services.workflows.engine import WorkflowEngine
from app.services.workflows.runtime import build_edge_states, build_node_states


@pytest.fixture
def db(tmp_path: Path) -> Iterator[Session]:
    db_path = tmp_path / "chat_stability.db"
    engine = create_engine(f"sqlite:///{db_path.as_posix()}", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.mark.asyncio
async def test_direct_agent_tool_failure_still_finishes_assistant_message(db: Session) -> None:
    user, conversation, user_message = _user_conversation_message(db, "请测试接口")
    agent = _agent(user, "Frontend Worker", "frontend", tools=["api.test"])
    db.add(agent)
    db.commit()
    calls: list[list[dict[str, Any]]] = []

    async def fake_stream_chat(messages: list[dict[str, Any]], **_: Any) -> Any:
        calls.append(messages)
        if len(calls) == 1:
            yield LLMStreamEvent(
                type="tool_calls",
                tool_calls=[
                    {
                        "id": "call-api",
                        "type": "function",
                        "function": {"name": "api.test", "arguments": '{"path": "/health"}'},
                    }
                ],
            )
            yield LLMStreamEvent(type="done", usage={})
            return
        yield LLMStreamEvent(type="delta", text="接口测试失败，我已停止继续调用。")
        yield LLMStreamEvent(type="done", usage={})

    with patch("app.services.agents.function_loop.ark_client.stream_chat", fake_stream_chat):
        with patch("app.services.agents.function_loop.execute_tool_by_name", new_callable=AsyncMock) as execute:
            execute.side_effect = RuntimeError("network down")
            with patch("app.services.agents.function_loop.event_bus.publish", new_callable=AsyncMock) as publish:
                result = await run_agent_function_call_loop(
                    db,
                    conversation=conversation,
                    user_message=user_message,
                    agent=agent,
                    prompt="请测试接口",
                    channel=f"conversation:{conversation.id}",
                    mode="unit-test",
                )

    assistant = db.scalar(select(Message).where(Message.sender_type == "agent"))
    assert assistant is not None
    assert assistant.status == "completed"
    assert result.tool_results[0]["status"] == "failed"
    assert not db.scalars(select(Message).where(Message.status == "streaming")).all()
    assert any(call.args[1] == "message_stop" for call in publish.await_args_list)
    assert len(calls) == 2
    assert any(item.get("role") == "tool" for item in calls[1])


@pytest.mark.asyncio
async def test_successful_tool_call_is_not_inserted_as_tool_runner_message(db: Session) -> None:
    user, conversation, _ = _user_conversation_message(db, "总结文件")
    db.commit()
    channel = f"conversation:{conversation.id}"
    success_context = {
        "executions": [
            {
                "tool_name": "file.summarize",
                "output": {
                    "status": "succeeded",
                    "conversation_id": conversation.id,
                    "summary": "done",
                },
            }
        ]
    }
    failure_context = {
        "executions": [
            {
                "tool_name": "file.summarize",
                "output": {
                    "status": "failed",
                    "conversation_id": conversation.id,
                    "error": "parse failed",
                },
            },
            {
                "tool_name": "sandbox.run",
                "output": {
                    "status": "failed",
                    "conversation_id": conversation.id,
                    "error": "command failed",
                },
            }
        ]
    }

    with patch("app.services.chat.artifacts.event_bus.publish", new_callable=AsyncMock):
        await _publish_tool_artifacts(db, channel, success_context)
        assert db.scalars(select(Message).where(Message.sender_name == "Tool Runner")).all() == []

        await _publish_tool_artifacts(db, channel, failure_context)

    tool_messages = db.scalars(select(Message).where(Message.sender_name == "Tool Runner")).all()
    assert len(tool_messages) == 1
    assert "file.summarize" in tool_messages[0].content["text"]


@pytest.mark.asyncio
async def test_retry_success_does_not_insert_failed_tool_runner_message(db: Session) -> None:
    _user, conversation, _message = _user_conversation_message(db, "运行脚本")
    channel = f"conversation:{conversation.id}"
    retry_context = {
        "executions": [
            {
                "tool_name": "sandbox.run",
                "output": {
                    "status": "failed",
                    "conversation_id": conversation.id,
                    "exit_code": 1,
                    "stderr": "missing file",
                },
            },
            {
                "tool_name": "sandbox.run",
                "output": {
                    "status": "succeeded",
                    "conversation_id": conversation.id,
                    "exit_code": 0,
                    "stdout": "ok",
                },
            },
        ]
    }

    with patch("app.services.chat.artifacts.event_bus.publish", new_callable=AsyncMock):
        await _publish_tool_artifacts(db, channel, retry_context)

    assert db.scalars(select(Message).where(Message.sender_name == "Tool Runner")).all() == []


@pytest.mark.asyncio
async def test_agent_tool_events_are_persisted_without_tool_runner_messages(db: Session) -> None:
    user, conversation, user_message = _user_conversation_message(db, "杩愯涓夋 sandbox")
    agent = _agent(user, "Frontend Worker", "frontend", tools=["sandbox.run"])
    db.add(agent)
    db.commit()
    calls: list[list[dict[str, Any]]] = []

    async def fake_stream_chat(messages: list[dict[str, Any]], **_: Any) -> Any:
        calls.append(messages)
        if len(calls) == 1:
            yield LLMStreamEvent(
                type="tool_calls",
                tool_calls=[
                    {
                        "id": f"call-sandbox-{index}",
                        "type": "function",
                        "function": {"name": "sandbox.run", "arguments": '{"command": "echo ok"}'},
                    }
                    for index in range(3)
                ],
            )
            yield LLMStreamEvent(type="done", usage={})
            return
        yield LLMStreamEvent(type="delta", text="sandbox 已完成。")
        yield LLMStreamEvent(type="done", usage={})

    async def fake_execute(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {
            "type": "tool",
            "tool_name": "sandbox.run",
            "status": "succeeded",
            "output": {
                "status": "succeeded",
                "stdout": "ok",
                "stderr": "",
                "exit_code": 0,
                "duration_ms": 12,
                "conversation_id": conversation.id,
            },
        }

    with patch("app.services.agents.function_loop.ark_client.stream_chat", fake_stream_chat):
        with patch("app.services.agents.function_loop.execute_tool_by_name", fake_execute):
            with patch("app.services.agents.function_loop.event_bus.publish", new_callable=AsyncMock) as publish:
                result = await run_agent_function_call_loop(
                    db,
                    conversation=conversation,
                    user_message=user_message,
                    agent=agent,
                    prompt="杩愯涓夋 sandbox",
                    channel=f"conversation:{conversation.id}",
                    mode="unit-test",
                )

    assistant = result.assistant
    assert assistant is not None
    assert assistant.status == "completed"
    tool_events = assistant.content["tool_events"]
    assert len(tool_events) == 3
    assert {event["tool_name"] for event in tool_events} == {"sandbox.run"}
    assert db.scalars(select(Message).where(Message.sender_name == "Tool Runner")).all() == []
    done_events = [call for call in publish.await_args_list if call.args[1] == "tool_call_done"]
    assert len(done_events) == 3
    assert all(call.args[2]["agent_message_id"] == assistant.id for call in done_events)
    assert done_events[0].args[2]["detail"]["tool_name"] == "sandbox.run"


@pytest.mark.asyncio
async def test_group_independent_workflow_runs_all_agents_on_repeated_rounds(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "group_rounds.db"
    engine = create_engine(f"sqlite:///{db_path.as_posix()}", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    db = factory()
    try:
        user = _user()
        conversation = Conversation(creator_id=user.id, chat_type="group", title="稳定性群聊", extra={})
        agents = [
            _agent(user, "Frontend Worker", "frontend"),
            _agent(user, "Backend Worker", "backend"),
            _agent(user, "Daily Chat Agent", "chat"),
        ]
        db.add_all([user, conversation, *agents])
        db.commit()
        workflow = _parallel_agent_workflow(conversation.id, agents)

        async def fake_agent_loop(session: Session, **kwargs: Any) -> AgentFunctionLoopResult:
            agent: Agent = kwargs["agent"]
            conv: Conversation = kwargs["conversation"]
            user_msg: Message = kwargs["user_message"]
            assert kwargs["emit_message"] is True
            assistant = Message(
                conversation_id=conv.id,
                sender_type="agent",
                sender_id=agent.id,
                sender_name=agent.name,
                content_type="text",
                content={"text": f"{agent.name}: {user_msg.content['text']}"},
                status="completed",
            )
            session.add(assistant)
            session.commit()
            return AgentFunctionLoopResult(
                assistant=assistant,
                text=assistant.content["text"],
                thinking="",
                tool_results=[],
                tool_context={"agent_name": agent.name},
            )

        with patch("app.services.workflows.engine.SessionLocal", side_effect=factory):
            with patch(
                "app.services.workflows.nodes.agent.run_agent_function_call_loop",
                side_effect=fake_agent_loop,
            ):
                for index, prompt in enumerate(["你们好", "分别说一下你们能做什么"], start=1):
                    user_message = Message(
                        conversation_id=conversation.id,
                        sender_type="user",
                        sender_id=user.id,
                        sender_name=user.display_name,
                        content_type="text",
                        content={"text": prompt},
                        status="sent",
                        extra={},
                    )
                    db.add(user_message)
                    db.flush()
                    task = Task(
                        conversation_id=conversation.id,
                        creator_id=user.id,
                        title=f"round-{index}",
                        description=prompt,
                        status="EXECUTING",
                        progress=10,
                    )
                    workflow_run = WorkflowRun(
                        conversation_id=conversation.id,
                        trigger_message_id=user_message.id,
                        started_by=user.id,
                        status="running",
                        mode="canvas",
                        workflow_snapshot=workflow,
                        node_states=build_node_states(workflow),
                        edge_states=build_edge_states(workflow),
                        progress=5,
                    )
                    db.add_all([task, workflow_run])
                    db.commit()

                    with patch("app.services.workflows.events.event_bus.publish", new_callable=AsyncMock):
                        result = await WorkflowEngine(
                            db,
                            conversation=conversation,
                            user_message=user_message,
                            task=task,
                            workflow_run=workflow_run,
                            workflow=workflow,
                            prompt=prompt,
                            channel=f"conversation:{conversation.id}",
                            agents=agents,
                        ).run()

                    assert len(result.agent_replies) == 3

        db.expire_all()
        replies = db.scalars(select(Message).where(Message.sender_type == "agent")).all()
        assert len(replies) == 6
        assert {message.sender_name for message in replies} == {
            "Frontend Worker",
            "Backend Worker",
            "Daily Chat Agent",
        }
        assert not db.scalars(select(Message).where(Message.status == "streaming")).all()
    finally:
        db.close()
        engine.dispose()


@pytest.mark.asyncio
async def test_generation_failure_closes_lingering_streaming_messages(db: Session) -> None:
    user, conversation, _ = _user_conversation_message(db, "会挂起吗")
    agent = _agent(user, "Daily Chat Agent", "chat")
    task = Task(
        conversation_id=conversation.id,
        creator_id=user.id,
        title="failure",
        description="failure",
        status="EXECUTING",
        progress=60,
    )
    assistant = Message(
        conversation_id=conversation.id,
        sender_type="agent",
        sender_id=agent.id,
        sender_name=agent.name,
        content_type="text",
        content={"text": ""},
        status="streaming",
    )
    db.add_all([agent, task, assistant])
    db.commit()

    with patch("app.services.chat.finalizer.event_bus.publish", new_callable=AsyncMock) as publish:
        await fail_generation(
            db,
            conversation=conversation,
            channel=f"conversation:{conversation.id}",
            task=task,
            workflow_run=None,
            reason="unit_test_failed",
            error=RuntimeError("boom"),
        )

    db.refresh(task)
    db.refresh(assistant)
    assert task.status == "FAILED"
    assert assistant.status == "failed"
    assert "异常结束" in assistant.content["text"]
    assert any(call.args[1] == "message_stop" for call in publish.await_args_list)
    assert any(call.args[1] == "generation_finished" for call in publish.await_args_list)


@pytest.mark.asyncio
async def test_image_attachment_without_vision_finishes_with_clear_reply(db: Session) -> None:
    user, conversation, user_message = _user_conversation_message(db, "这个图片是什么")
    user_message.content = {
        "text": "这个图片是什么",
        "attachments": [
            {
                "file_id": "image-1",
                "filename": "demo.png",
                "content_type": "image/png",
                "size": 12,
                "parse_status": "stored",
                "extracted_text": "[图片文件：demo.png，可交给视觉模型或 OCR 工具继续识别]",
                "metadata": {"extractor": "vision_entry", "vision_status": "ready_for_vision_model"},
            }
        ],
    }
    agent = _agent(user, "Writing Agent", "writer")
    db.add(agent)
    db.commit()

    async def fail_if_called(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("image without vision should not call model")

    with patch("app.services.agents.function_loop.ark_client.stream_chat", fail_if_called):
        with patch("app.services.agents.function_loop.event_bus.publish", new_callable=AsyncMock) as publish:
            result = await run_agent_function_call_loop(
                db,
                conversation=conversation,
                user_message=user_message,
                agent=agent,
                prompt="这个图片是什么",
                channel=f"conversation:{conversation.id}",
                mode="unit-test",
            )

    assistant = result.assistant
    assert assistant is not None
    assert assistant.status == "completed"
    assert "未启用视觉/OCR解析" in assistant.content["text"]
    assert "无法判断图片内容" in assistant.content["text"]
    assert not db.scalars(select(Message).where(Message.status == "streaming")).all()
    assert any(call.args[1] == "message_stop" for call in publish.await_args_list)


@pytest.mark.asyncio
async def test_pdf_attachment_text_enters_context_once_and_finishes(db: Session) -> None:
    user, conversation, user_message = _user_conversation_message(db, "总结一下这个文件")
    user_message.content = {
        "text": "总结一下这个文件",
        "attachments": [
            {
                "file_id": "pdf-1",
                "filename": "report.pdf",
                "content_type": "application/pdf",
                "size": 100,
                "parse_status": "parsed",
                "extracted_text": "PDF 项目方案正文，需要总结关键目标和风险。",
                "metadata": {"extractor": "pypdf"},
            }
        ],
    }
    agent = _agent(user, "Writing Agent", "writer")
    db.add(agent)
    db.commit()

    async def fake_stream(messages: list[dict[str, Any]], **_kwargs: Any) -> Any:
        serialized = "\n".join(str(item.get("content")) for item in messages)
        assert "PDF 项目方案正文" in serialized
        assert messages[-1]["content"] == "总结一下这个文件"
        assert serialized.count("PDF 项目方案正文") == 1
        yield LLMStreamEvent(type="delta", text="文件主要说明项目目标和风险。")
        yield LLMStreamEvent(type="done", usage={})

    with patch("app.services.agents.function_loop.ark_client.stream_chat", fake_stream):
        with patch("app.services.agents.function_loop.event_bus.publish", new_callable=AsyncMock) as publish:
            result = await run_agent_function_call_loop(
                db,
                conversation=conversation,
                user_message=user_message,
                agent=agent,
                prompt="总结一下这个文件",
                channel=f"conversation:{conversation.id}",
                mode="unit-test",
            )

    assert result.assistant is not None
    assert result.assistant.status == "completed"
    assert "项目目标和风险" in result.assistant.content["text"]
    assert not db.scalars(select(Message).where(Message.status == "streaming")).all()
    assert any(call.args[1] == "message_stop" for call in publish.await_args_list)


@pytest.mark.asyncio
async def test_empty_extracted_text_attachment_finishes_with_clear_reply(db: Session) -> None:
    user, conversation, user_message = _user_conversation_message(db, "总结一下这个文件")
    user_message.content = {
        "text": "总结一下这个文件",
        "attachments": [
            {
                "file_id": "empty-1",
                "filename": "empty.docx",
                "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "size": 10,
                "parse_status": "stored",
                "extracted_text": "",
                "metadata": {"extractor": "python-docx"},
            }
        ],
    }
    agent = _agent(user, "Writing Agent", "writer")
    db.add(agent)
    db.commit()

    async def fail_if_called(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("empty attachment should not call model")

    with patch("app.services.agents.function_loop.ark_client.stream_chat", fail_if_called):
        with patch("app.services.agents.function_loop.event_bus.publish", new_callable=AsyncMock) as publish:
            result = await run_agent_function_call_loop(
                db,
                conversation=conversation,
                user_message=user_message,
                agent=agent,
                prompt="总结一下这个文件",
                channel=f"conversation:{conversation.id}",
                mode="unit-test",
            )

    assert result.assistant is not None
    assert result.assistant.status == "completed"
    assert "未提取到可读文本" in result.assistant.content["text"]
    assert not db.scalars(select(Message).where(Message.status == "streaming")).all()
    assert any(call.args[1] == "message_stop" for call in publish.await_args_list)


@pytest.mark.asyncio
async def test_model_exception_path_does_not_leave_streaming_message(db: Session) -> None:
    user, conversation, user_message = _user_conversation_message(db, "你好")
    agent = _agent(user, "Daily Chat Agent", "chat")
    db.add(agent)
    db.commit()

    async def broken_stream(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("model socket closed")
        yield LLMStreamEvent(type="done", usage={})

    with patch("app.services.agents.function_loop.ark_client.stream_chat", broken_stream):
        with patch("app.services.agents.function_loop.event_bus.publish", new_callable=AsyncMock) as publish:
            result = await run_agent_function_call_loop(
                db,
                conversation=conversation,
                user_message=user_message,
                agent=agent,
                prompt="你好",
                channel=f"conversation:{conversation.id}",
                mode="unit-test",
            )

    assert result.assistant is not None
    assert result.assistant.status == "completed"
    assert "模型调用异常" in result.assistant.content["text"]
    assert not db.scalars(select(Message).where(Message.status == "streaming")).all()
    assert any(call.args[1] == "message_stop" for call in publish.await_args_list)


@pytest.mark.asyncio
async def test_independent_group_completion_updates_last_preview(db: Session) -> None:
    user, conversation, user_message = _user_conversation_message(db, "群聊问题")
    conversation.chat_type = "group"
    task = Task(
        conversation_id=conversation.id,
        creator_id=user.id,
        title="group",
        description="group",
        status="EXECUTING",
        progress=80,
    )
    workflow = _parallel_agent_workflow(conversation.id, [])
    workflow_run = WorkflowRun(
        conversation_id=conversation.id,
        trigger_message_id=user_message.id,
        started_by=user.id,
        status="running",
        mode="canvas",
        workflow_snapshot=workflow,
        node_states=build_node_states(workflow),
        edge_states=build_edge_states(workflow),
        progress=80,
    )
    db.add_all([task, workflow_run])
    db.commit()

    with patch("app.services.chat.orchestrator.event_bus.publish", new_callable=AsyncMock):
        await _complete_independent_group(
            db,
            conversation,
            task,
            workflow_run,
            [],
            [
                {"agent_name": "Frontend Worker", "text": "前端已回复"},
                {"agent_name": "Backend Worker", "text": "后端已回复"},
            ],
            f"conversation:{conversation.id}",
        )

    db.refresh(conversation)
    db.refresh(task)
    assert task.status == "COMPLETED"
    assert "Frontend Worker" in conversation.last_message_preview
    assert "正在回答" not in conversation.last_message_preview


def _user() -> User:
    suffix = uuid4().hex
    return User(
        id=f"user-{suffix[:24]}",
        email=f"chat-stability-{suffix}@example.com",
        username=f"chat-stability-{suffix}",
        password_hash="x",
        display_name="演示用户",
    )


def _agent(user: User, name: str, agent_type: str, tools: list[str] | None = None) -> Agent:
    return Agent(
        owner_id=user.id,
        name=name,
        type=agent_type,
        description=f"{name} description",
        config={"tools": tools or []},
        capabilities=[],
    )


def _user_conversation_message(db: Session, text: str) -> tuple[User, Conversation, Message]:
    user = _user()
    conversation = Conversation(creator_id=user.id, chat_type="single", title="稳定性单聊", extra={})
    db.add_all([user, conversation])
    db.flush()
    message = Message(
        conversation_id=conversation.id,
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
    db.refresh(conversation)
    db.refresh(message)
    return user, conversation, message


def _parallel_agent_workflow(conversation_id: str, agents: list[Agent]) -> dict[str, Any]:
    nodes = [{"id": "start", "type": "start", "title": "Start"}]
    for agent in agents:
        nodes.append(
            {
                "id": f"agent-{agent.id[:8]}",
                "type": "agent",
                "title": agent.name,
                "agent_id": agent.id,
                "config": {"agent_id": agent.id},
            }
        )
    nodes.append({"id": "end", "type": "end", "title": "End"})
    agent_node_ids = [node["id"] for node in nodes if node["id"].startswith("agent-")]
    return {
        "conversation_id": conversation_id,
        "mode": "all_agents_independent",
        "output_mode": "independent_messages",
        "nodes": nodes,
        "edges": [["start", node_id] for node_id in agent_node_ids]
        + [[node_id, "end"] for node_id in agent_node_ids],
    }
