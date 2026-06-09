import asyncio

import pytest

from agent_runtime.context.blackboard import BlackboardManager
from agent_runtime.core.protocol import (
    AGENT_REPORT,
    CONTROL_ASSIGN,
    CONTROL_COMPLETE,
    SCHEDULER_DECISION,
    SCHEDULER_PLAN,
    SCHEDULER_SUMMARY,
    USER_INPUT,
)
from agent_runtime.core.types import AgentConfig, Event, SchedulingDecision
from agent_runtime.runtime.agent_loop import AgentLoop
from agent_runtime.runtime.agent_actor import AgentActor
from agent_runtime.runtime.event_dispatcher import EventDispatcher
from agent_runtime.strategies.scheduler_agent import SchedulerAgent
from agent_runtime.strategies.tech_lead import TechLeadScheduler
from model_provider.core.interfaces import ChatResponse


@pytest.mark.asyncio
async def test_scheduler_agent_turns_user_input_into_control_assign():
    bus = EventDispatcher()
    blackboard = BlackboardManager(event_bus=bus)
    events: list[Event] = []
    bus.subscribe("*", lambda event: _append(events, event), target="*")
    scheduler = SchedulerAgent(
        session_id="sess_scheduler",
        agents={
            "frontend": AgentConfig(id="frontend", name="Frontend", system_prompt="build ui"),
            "backend": AgentConfig(id="backend", name="Backend", system_prompt="build api"),
        },
        event_bus=bus,
        blackboard_mgr=blackboard,
        model_provider=None,
    )
    scheduler.start()

    assert isinstance(scheduler, AgentActor)

    await bus.publish(Event(type=USER_INPUT, payload={"content": "build a page"}, source="user"))
    decision = await _wait_for(events, SCHEDULER_DECISION)
    assign = await _wait_for(events, CONTROL_ASSIGN)
    await scheduler.stop()

    assert decision.payload["decision"]["decision_type"] == "assign"
    assert assign.target == "frontend"
    stored = await blackboard.get("sess_scheduler")
    assert stored is not None
    assert any(item.get("type") == "scheduler_agent_decision" for item in stored["raw_history"])


@pytest.mark.asyncio
async def test_scheduler_agent_publishes_plan_inputs_and_summary():
    bus = EventDispatcher()
    blackboard = BlackboardManager(event_bus=bus)
    events: list[Event] = []
    bus.subscribe("*", lambda event: _append(events, event), target="*")
    scheduler = SchedulerAgent(
        session_id="sess_scheduler_plan",
        agents={
            "frontend": AgentConfig(id="frontend", name="Frontend", system_prompt="build ui", role="frontend"),
            "backend": AgentConfig(id="backend", name="Backend", system_prompt="build api", role="backend"),
        },
        event_bus=bus,
        blackboard_mgr=blackboard,
        model_provider=None,
    )
    scheduler.start()

    await bus.publish(Event(type=USER_INPUT, payload={"content": "build frontend and backend"}, source="user"))
    plan = await _wait_for(events, SCHEDULER_PLAN)
    first_assign = await _wait_for(events, CONTROL_ASSIGN)

    await bus.publish(
        Event(
            type=AGENT_REPORT,
            payload={
                "agent_id": "frontend",
                "task": "build frontend",
                "work_product": "frontend done",
                "tool_events": [{"round": 1, "results": [{"tool": "artifact.create_html"}]}],
                "report": {
                    "agent_id": "frontend",
                    "state": "completed",
                    "will": "complete",
                    "confidence": 0.9,
                    "rationale": "UI complete",
                },
            },
            source="agent:frontend",
        )
    )
    await bus.publish(
        Event(
            type=AGENT_REPORT,
            payload={
                "agent_id": "backend",
                "task": "build backend",
                "work_product": "backend done",
                "report": {
                    "agent_id": "backend",
                    "state": "completed",
                    "will": "complete",
                    "confidence": 0.8,
                    "rationale": "API complete",
                },
            },
            source="agent:backend",
        )
    )
    summary = await _wait_for(events, SCHEDULER_SUMMARY)
    complete = await _wait_for(events, CONTROL_COMPLETE)
    await scheduler.stop()

    assignments = [event for event in events if event.type == CONTROL_ASSIGN]
    assert [item["agent_id"] for item in plan.payload["plan"]] == ["frontend", "backend"]
    assert first_assign.payload["task_input"]["user_request"] == "build frontend and backend"
    assert first_assign.payload["task_input"]["plan"][0]["agent_id"] == "frontend"
    assert {event.target for event in assignments} == {"frontend", "backend"}
    assert summary.payload["status"] == "completed"
    assert summary.payload["completed_agent_ids"] == ["frontend", "backend"]
    assert "Frontend" in summary.payload["final_answer"]
    assert "## 最终成品" in summary.payload["final_answer"]
    assert summary.payload["final_product"]["type"] == "integrated"
    assert "## 归集" in summary.payload["final_answer"]
    assert summary.payload["compliance_checks"]
    assert complete.payload["summary"]["agent_outputs"][0]["agent_id"] == "frontend"


def test_scheduler_final_answer_keeps_single_agent_product_direct():
    bus = EventDispatcher()
    scheduler = SchedulerAgent(
        session_id="sess_scheduler_single_product",
        agents={
            "daily": AgentConfig(id="daily", name="Daily Chat Agent", system_prompt="chat", role="chat"),
        },
        event_bus=bus,
        blackboard_mgr=BlackboardManager(event_bus=bus),
        model_provider=None,
    )
    scheduler.current_task = "say hello"
    scheduler._turn_plan = scheduler._build_turn_plan(scheduler.current_task)
    scheduler._record_agent_output(
        {
            "agent_id": "daily",
            "task": "say hello",
            "work_product": "你好，我在。",
            "report": {
                "agent_id": "daily",
                "state": "completed",
                "will": "complete",
                "confidence": 1.0,
            },
        },
        _completed_report("daily"),
    )

    summary = scheduler._runtime_summary()

    assert summary["final_answer"] == "你好，我在。"
    assert summary["final_product"]["type"] == "single"
    assert summary["final_product"]["content"] == "你好，我在。"
    assert "协作复盘" not in summary["final_answer"]


def test_scheduler_selects_suitable_subset_instead_of_using_every_group_agent():
    bus = EventDispatcher()
    scheduler = SchedulerAgent(
        session_id="sess_scheduler_three_agent_default",
        agents={
            "planner": AgentConfig(id="planner", name="Planner", system_prompt="plan", role="planner"),
            "writer": AgentConfig(id="writer", name="Writer", system_prompt="write", role="writer"),
            "analyst": AgentConfig(id="analyst", name="Analyst", system_prompt="analyze", role="analyst"),
        },
        event_bus=bus,
        blackboard_mgr=BlackboardManager(event_bus=bus),
        model_provider=None,
    )

    plan = scheduler._build_turn_plan("整理一份产品发布方案")

    assert [item["agent_id"] for item in plan] == ["planner"]
    assert plan[0]["stage"] == 1
    assert plan[0]["depends_on"] == []

    complex_plan = scheduler._build_turn_plan(
        "组织多智能体完成新产品发布准备包，包括发布节奏、用户沟通和指标分析。"
    )

    assert [item["agent_id"] for item in complex_plan] == ["planner", "writer", "analyst"]
    assert complex_plan[1]["depends_on"] == ["planner"]
    assert complex_plan[2]["depends_on"] == ["planner"]


def test_scheduler_single_mention_does_not_expand_to_group_collaboration():
    bus = EventDispatcher()
    scheduler = SchedulerAgent(
        session_id="sess_scheduler_three_agent_mention",
        agents={
            "planner": AgentConfig(id="planner", name="Planner", system_prompt="plan", role="planner"),
            "writer": AgentConfig(id="writer", name="Writer", system_prompt="write", role="writer"),
            "analyst": AgentConfig(id="analyst", name="Analyst", system_prompt="analyze", role="analyst"),
        },
        event_bus=bus,
        blackboard_mgr=BlackboardManager(event_bus=bus),
        model_provider=None,
    )

    plan = scheduler._build_turn_plan("@Writer 帮我润色这段话")

    assert [item["agent_id"] for item in plan] == ["writer"]


def test_scheduler_group_collaboration_mentions_roles_without_narrowing_to_them():
    bus = EventDispatcher()
    scheduler = SchedulerAgent(
        session_id="sess_scheduler_role_names_in_group_task",
        agents={
            "frontend": AgentConfig(id="frontend", name="Frontend Worker", system_prompt="build ui", role="frontend"),
            "writer": AgentConfig(id="writer", name="Writing Agent", system_prompt="write", role="writer"),
            "reviewer": AgentConfig(id="reviewer", name="Reviewer", system_prompt="review", role="reviewer"),
            "deploy": AgentConfig(id="deploy", name="Deploy Agent", system_prompt="deploy", role="deploy"),
        },
        event_bus=bus,
        blackboard_mgr=BlackboardManager(event_bus=bus),
        model_provider=None,
    )

    plan = scheduler._build_turn_plan(
        "请组织这四个智能体完成发布复盘交付：生成 HTML 和文档，Reviewer 复核，Deploy Agent 部署预览。"
    )

    assert [item["agent_id"] for item in plan] == ["frontend", "writer", "reviewer", "deploy"]
    assert plan[2]["depends_on"] == ["frontend", "writer"]
    assert plan[3]["depends_on"] == ["frontend", "writer", "reviewer"]


def test_scheduler_recognizes_writing_role_for_downloadable_documents():
    bus = EventDispatcher()
    scheduler = SchedulerAgent(
        session_id="sess_scheduler_writing_role",
        agents={
            "frontend": AgentConfig(id="frontend", name="Frontend Worker", system_prompt="build ui", role="frontend"),
            "writing": AgentConfig(id="writing", name="Writing Agent", system_prompt="write", role="writing"),
            "reviewer": AgentConfig(id="reviewer", name="Reviewer", system_prompt="review", role="reviewer"),
            "deploy": AgentConfig(id="deploy", name="Deploy Agent", system_prompt="deploy", role="deploy"),
        },
        event_bus=bus,
        blackboard_mgr=BlackboardManager(event_bus=bus),
        model_provider=None,
    )

    plan = scheduler._build_turn_plan(
        "请组织这四个智能体完成轻量发布复盘交付：生成可预览 HTML 总览页和可下载文档，Reviewer 复核，Deploy Agent 部署预览。"
    )

    assert [item["agent_id"] for item in plan] == ["frontend", "writing", "reviewer", "deploy"]
    assert plan[1]["task"] == "生成可下载交付文档"
    assert plan[2]["depends_on"] == ["frontend", "writing"]
    assert plan[3]["depends_on"] == ["frontend", "writing", "reviewer"]


def test_scheduler_final_product_preserves_artifact_references():
    bus = EventDispatcher()
    scheduler = SchedulerAgent(
        session_id="sess_scheduler_artifact_product",
        agents={
            "frontend": AgentConfig(id="frontend", name="Frontend", system_prompt="build ui", role="frontend"),
        },
        event_bus=bus,
        blackboard_mgr=BlackboardManager(event_bus=bus),
        model_provider=None,
    )
    scheduler.current_task = "build an html page"
    scheduler._turn_plan = scheduler._build_turn_plan(scheduler.current_task)
    scheduler._record_agent_output(
        {
            "agent_id": "frontend",
            "task": "build html",
            "work_product": "HTML page completed.",
            "output": {
                "work_product": "HTML page completed.",
                "artifact_id": "artifact-1",
                "preview_message_id": "preview-1",
                "filename": "index.html",
            },
            "report": {
                "agent_id": "frontend",
                "state": "completed",
                "will": "complete",
                "confidence": 1.0,
            },
        },
        _completed_report("frontend"),
    )

    summary = scheduler._runtime_summary()

    assert summary["final_answer"].startswith("HTML page completed.")
    assert summary["final_product"]["artifacts"][0]["artifact_id"] == "artifact-1"
    assert summary["final_deliverable"]["source_reviews"][0]["artifacts"][0]["preview_message_id"] == "preview-1"


def test_scheduler_collaborative_final_answer_summarizes_without_raw_transcript_dump():
    bus = EventDispatcher()
    scheduler = SchedulerAgent(
        session_id="sess_scheduler_integrated_summary",
        agents={
            "frontend": AgentConfig(id="frontend", name="Frontend Worker", system_prompt="build ui", role="frontend"),
            "backend": AgentConfig(id="backend", name="Backend Worker", system_prompt="build api", role="backend"),
            "reviewer": AgentConfig(id="reviewer", name="Reviewer", system_prompt="review", role="reviewer"),
        },
        event_bus=bus,
        blackboard_mgr=BlackboardManager(event_bus=bus),
        model_provider=None,
    )
    scheduler.current_task = "组织多智能体完成企业知识库问答 MVP"
    scheduler._turn_plan = scheduler._build_turn_plan(scheduler.current_task)
    frontend_raw = (
        "Frontend Worker 已完成企业知识库问答 MVP 可预览 Web 原型的生成与自检："
        "包含文档上传区、知识库列表、问答输入、引用来源面板、索引状态和错误提示。"
        "这是不应该被 Team Leader 原封不动整段复制的原始聊天内容。"
    )
    backend_raw = (
        "Backend Worker 已完成 API 草案、核心数据模型、RAG 检索链路、流式问答协议，"
        "并完成上传、索引状态、问答返回三个接口伪执行检查。"
    )
    for agent_id, work_product, output in [
        (
            "frontend",
            frontend_raw,
            {
                "artifact_id": "artifact-web",
                "title": "知识库问答 MVP Web 原型",
                "preview_url": "/preview-web",
                "export_url": "/export-web",
            },
        ),
        (
            "backend",
            backend_raw,
            {
                "artifact_id": "artifact-doc",
                "title": "知识库问答 MVP 后端方案",
                "preview_url": "/preview-doc",
                "export_url": "/export-doc",
            },
        ),
        ("reviewer", "Reviewer 已完成需求矩阵和安全边界验收。", {}),
    ]:
        scheduler._record_agent_output(
            {
                "agent_id": agent_id,
                "task": "enterprise knowledge base MVP",
                "work_product": work_product,
                "output": output,
                "tool_events": [{"round": 1, "results": [{"tool": "artifact.create_html", "output": output}]}]
                if output
                else [],
            },
            _completed_report(agent_id),
        )

    summary = scheduler._runtime_summary()
    final_answer = summary["final_answer"]

    assert summary["final_product"]["type"] == "integrated"
    assert "## 最终成品" in final_answer
    assert "## 归集" in final_answer
    assert "## 链路" in final_answer
    assert "## 校验" in final_answer
    assert "## 产物" in final_answer
    assert "## 风险" in final_answer
    assert "知识库问答 MVP Web 原型" in final_answer
    assert frontend_raw not in final_answer
    assert backend_raw not in final_answer
    assert summary["final_deliverable"]["source_reviews"][0]["output"] == frontend_raw


def test_scheduler_collaborative_final_answer_adapts_to_non_engineering_agents():
    bus = EventDispatcher()
    scheduler = SchedulerAgent(
        session_id="sess_scheduler_dynamic_summary",
        agents={
            "planner": AgentConfig(id="planner", name="Launch Planner", system_prompt="plan", role="planner"),
            "analyst": AgentConfig(id="analyst", name="Market Analyst", system_prompt="analyze", role="analyst"),
            "writer": AgentConfig(id="writer", name="Comms Writer", system_prompt="write", role="writer"),
            "reviewer": AgentConfig(id="reviewer", name="Risk Reviewer", system_prompt="review", role="reviewer"),
        },
        event_bus=bus,
        blackboard_mgr=BlackboardManager(event_bus=bus),
        model_provider=None,
    )
    scheduler.current_task = "组织多智能体完成新产品发布准备包，包括发布节奏、指标分析、用户沟通、风险清单和验收检查。"
    scheduler._turn_plan = scheduler._build_turn_plan(scheduler.current_task)

    assert [item["agent_id"] for item in scheduler._turn_plan] == [
        "planner",
        "analyst",
        "writer",
        "reviewer",
    ]
    assert scheduler._turn_plan[0]["stage"] == 1
    assert scheduler._turn_plan[1]["depends_on"] == ["planner"]
    assert scheduler._turn_plan[2]["depends_on"] == ["planner"]
    assert scheduler._turn_plan[3]["depends_on"] == ["planner", "analyst", "writer"]

    raw_outputs = {
        "planner": "发布节奏分为预热、灰度、正式发布、复盘四步，并列出负责人和验收口径。",
        "analyst": "分析了目标用户、竞品窗口、指标口径和关键假设。",
        "writer": "完成用户公告、FAQ、站内信和客服话术草案。",
        "reviewer": "完成风险清单、验收检查、合规边界和回滚条件复核。",
    }
    for agent_id, work_product in raw_outputs.items():
        scheduler._record_agent_output(
            {
                "agent_id": agent_id,
                "task": scheduler._plan_item_for_agent(agent_id)["task"],
                "work_product": work_product,
            },
            _completed_report(agent_id),
        )

    summary = scheduler._runtime_summary()
    final_answer = summary["final_answer"]

    assert "## 最终成品" in final_answer
    assert "## 归集" in final_answer
    assert "## 链路" in final_answer
    assert "## 校验" in final_answer
    assert "## 产物" in final_answer
    assert "## 风险" in final_answer
    assert "规划与任务拆解" in final_answer
    assert "分析洞察与依据" in final_answer
    assert "内容撰写与沟通材料" in final_answer
    assert "质量校验与风险检查" in final_answer
    assert "前端原型与交互" not in final_answer
    assert "后端接口与知识库链路" not in final_answer
    assert raw_outputs["writer"] not in final_answer
    assert "本轮无独立预览卡片" in final_answer
    assert summary["final_deliverable"]["source_reviews"][2]["output"] == raw_outputs["writer"]


def test_scheduler_final_answer_lists_nested_tool_artifacts():
    bus = EventDispatcher()
    scheduler = SchedulerAgent(
        session_id="sess_scheduler_nested_artifacts",
        agents={
            "frontend": AgentConfig(id="frontend", name="Frontend Worker", system_prompt="build ui", role="frontend"),
            "writer": AgentConfig(id="writer", name="Writing Agent", system_prompt="write", role="writer"),
            "reviewer": AgentConfig(id="reviewer", name="Reviewer", system_prompt="review", role="reviewer"),
        },
        event_bus=bus,
        blackboard_mgr=BlackboardManager(event_bus=bus),
        model_provider=None,
    )
    scheduler.current_task = "组织多智能体完成新产品发布准备包"
    scheduler._turn_plan = scheduler._build_turn_plan(scheduler.current_task)
    scheduler._record_agent_output(
        {
            "agent_id": "frontend",
            "task": "生成 HTML 预览",
            "work_product": "HTML 预览页面已生成，可在产物卡片中查看。",
            "tool_events": [
                {
                    "agent_id": "frontend",
                    "round": 1,
                    "results": [
                        {
                            "tool": "artifact.create_html",
                            "success": True,
                            "result": {
                                "type": "tool",
                                "tool_name": "artifact.create_html",
                                "status": "succeeded",
                                "output": {
                                    "artifact_id": "artifact-html",
                                    "artifact": {
                                        "id": "artifact-html",
                                        "title": "发布准备包 HTML 预览",
                                        "preview_url": "/api/v1/artifacts/artifact-html/preview",
                                        "export_url": "/api/v1/artifacts/artifact-html/export?format=html",
                                    },
                                    "format": "html",
                                    "media_type": "text/html",
                                    "preview_message_id": "preview-html",
                                },
                            },
                        }
                    ],
                }
            ],
        },
        _completed_report("frontend"),
    )
    scheduler._record_agent_output(
        {
            "agent_id": "writer",
            "task": "生成 Word 文档",
            "work_product": "正式发布准备包文档已生成。",
            "tool_events": [
                {
                    "agent_id": "writer",
                    "round": 1,
                    "results": [
                        {
                            "tool": "artifact.create_docx",
                            "success": True,
                            "result": {
                                "output": {
                                    "artifact_id": "artifact-docx",
                                    "artifact": {
                                        "title": "新产品发布准备包 Word 文档",
                                        "preview_url": "/api/v1/artifacts/artifact-docx/preview",
                                        "export_url": "/api/v1/artifacts/artifact-docx/export?format=docx",
                                    },
                                    "format": "docx",
                                    "preview_message_id": "preview-docx",
                                }
                            },
                        }
                    ],
                }
            ],
        },
        _completed_report("writer"),
    )
    scheduler._record_agent_output(
        {
            "agent_id": "reviewer",
            "task": "复核发布准备包",
            "work_product": "复核通过。",
        },
        _completed_report("reviewer"),
    )

    summary = scheduler._runtime_summary()
    artifacts = summary["final_product"]["artifacts"]
    final_answer = summary["final_answer"]

    assert [artifact["artifact_id"] for artifact in artifacts] == ["artifact-html", "artifact-docx"]
    assert artifacts[0]["title"] == "发布准备包 HTML 预览"
    assert artifacts[1]["title"] == "新产品发布准备包 Word 文档"
    assert "## 产物" in final_answer
    assert "发布准备包 HTML 预览" in final_answer
    assert "新产品发布准备包 Word 文档" in final_answer
    assert "本轮无独立预览卡片" not in final_answer


def test_scheduler_final_product_surfaces_empty_tool_output():
    bus = EventDispatcher()
    scheduler = SchedulerAgent(
        session_id="sess_scheduler_empty_tool_output",
        agents={
            "frontend": AgentConfig(id="frontend", name="Frontend Worker", system_prompt="build ui", role="frontend"),
            "backend": AgentConfig(id="backend", name="Backend Worker", system_prompt="build api", role="backend"),
        },
        event_bus=bus,
        blackboard_mgr=BlackboardManager(event_bus=bus),
        model_provider=None,
    )
    scheduler.current_task = "build frontend and backend"
    scheduler._turn_plan = scheduler._build_turn_plan(scheduler.current_task)
    scheduler._record_agent_output(
        {
            "agent_id": "frontend",
            "task": "build frontend",
            "work_product": "",
            "tool_events": [
                {
                    "round": 1,
                    "results": [
                        {
                            "tool": "artifact.create_html",
                            "success": False,
                            "error": "bad arguments",
                        }
                    ],
                }
            ],
            "report": {
                "agent_id": "frontend",
                "state": "completed",
                "will": "complete",
                "confidence": 0.5,
                "rationale": "claimed UI completion",
            },
        },
        _completed_report("frontend"),
    )
    scheduler._record_agent_output(
        {
            "agent_id": "backend",
            "task": "build backend",
            "work_product": "backend done",
        },
        _completed_report("backend"),
    )

    summary = scheduler._runtime_summary()
    sections = summary["final_product"]["sections"]
    frontend = next(item for item in sections if item["agent_name"] == "Frontend Worker")

    assert "未形成可直接展示的正文成果" in frontend["content"]
    assert "工具调用次数：1" in frontend["content"]
    assert "Frontend Worker" in summary["final_answer"]


def test_scheduler_agent_repairs_single_assign_to_planned_parallel_targets():
    bus = EventDispatcher()
    scheduler = SchedulerAgent(
        session_id="sess_scheduler_plan_repair",
        agents={
            "frontend": AgentConfig(id="frontend", name="Frontend", system_prompt="build ui", role="frontend"),
            "backend": AgentConfig(id="backend", name="Backend", system_prompt="build api", role="backend"),
        },
        event_bus=bus,
        blackboard_mgr=BlackboardManager(event_bus=bus),
        model_provider=None,
    )
    scheduler.current_task = "build frontend and backend"
    scheduler._turn_plan = scheduler._build_turn_plan(scheduler.current_task)

    repaired = scheduler._repair_decision(
        SchedulingDecision(
            decision_type="assign",
            target_agent_id="frontend",
            target_agent_ids=["frontend"],
            task_description="build frontend",
        ),
        reports=list(scheduler._initial_reports().values()),
    )

    assert repaired.decision_type == "parallel"
    assert repaired.target_agent_ids == ["frontend", "backend"]


def test_scheduler_agent_waits_for_inflight_planned_targets():
    bus = EventDispatcher()
    scheduler = SchedulerAgent(
        session_id="sess_scheduler_inflight",
        agents={
            "frontend": AgentConfig(id="frontend", name="Frontend", system_prompt="build ui", role="frontend"),
            "backend": AgentConfig(id="backend", name="Backend", system_prompt="build api", role="backend"),
        },
        event_bus=bus,
        blackboard_mgr=BlackboardManager(event_bus=bus),
        model_provider=None,
    )
    scheduler.current_task = "build frontend and backend"
    scheduler._turn_plan = scheduler._build_turn_plan(scheduler.current_task)
    scheduler._assigned_agent_ids = {"frontend", "backend"}
    scheduler._inflight_agent_ids = {"backend"}
    scheduler.reports["frontend"] = _completed_report("frontend")

    repaired = scheduler._repair_decision(
        SchedulingDecision(
            decision_type="complete",
            task_description="build frontend and backend",
        ),
        reports=[scheduler.reports["frontend"]],
    )

    assert repaired.decision_type == "wait"
    assert repaired.target_agent_ids == ["backend"]
    assert repaired.fallback_reason == "complete_guard_inflight_agents"


def test_scheduler_agent_dispatches_collaboration_plan_by_dependency_stage():
    bus = EventDispatcher()
    scheduler = SchedulerAgent(
        session_id="sess_scheduler_stages",
        agents={
            "frontend": AgentConfig(id="frontend", name="Frontend", system_prompt="build ui", role="frontend"),
            "backend": AgentConfig(id="backend", name="Backend", system_prompt="build api", role="backend"),
            "qa": AgentConfig(id="qa", name="QA Reviewer", system_prompt="review", role="qa"),
            "devops": AgentConfig(id="devops", name="DevOps", system_prompt="deploy", role="deploy"),
        },
        event_bus=bus,
        blackboard_mgr=BlackboardManager(event_bus=bus),
        model_provider=None,
    )
    scheduler.current_task = "build frontend backend qa deploy"
    scheduler._turn_plan = scheduler._build_turn_plan(scheduler.current_task)

    first = scheduler._repair_decision(
        SchedulingDecision(
            decision_type="parallel",
            target_agent_id="frontend",
            target_agent_ids=["frontend", "backend", "qa", "devops"],
            task_description=scheduler.current_task,
        ),
        reports=list(scheduler._initial_reports().values()),
    )
    assert first.decision_type == "parallel"
    assert first.target_agent_ids == ["frontend", "backend"]

    scheduler.reports["frontend"] = _completed_report("frontend")
    scheduler.reports["backend"] = _completed_report("backend")
    second = scheduler._repair_decision(
        SchedulingDecision(decision_type="complete", task_description=scheduler.current_task),
        reports=[scheduler.reports["frontend"], scheduler.reports["backend"]],
    )
    assert second.decision_type == "assign"
    assert second.target_agent_ids == ["qa"]
    assert second.fallback_reason == "complete_guard_ready_stage"

    scheduler.reports["qa"] = _completed_report("qa")
    third = scheduler._repair_decision(
        SchedulingDecision(decision_type="complete", task_description=scheduler.current_task),
        reports=[scheduler.reports["frontend"], scheduler.reports["backend"], scheduler.reports["qa"]],
    )
    assert third.decision_type == "assign"
    assert third.target_agent_ids == ["devops"]


def test_scheduler_agent_recognizes_chinese_collaboration_task():
    bus = EventDispatcher()
    scheduler = SchedulerAgent(
        session_id="sess_scheduler_chinese_collaboration",
        agents={
            "frontend": AgentConfig(id="frontend", name="Frontend Agent", system_prompt="build ui", role="frontend"),
            "backend": AgentConfig(id="backend", name="Backend Agent", system_prompt="build api", role="backend"),
            "qa": AgentConfig(id="qa", name="QA Agent", system_prompt="verify", role="qa"),
            "devops": AgentConfig(id="devops", name="DevOps Agent", system_prompt="release", role="deploy"),
        },
        event_bus=bus,
        blackboard_mgr=BlackboardManager(event_bus=bus),
        model_provider=None,
    )

    plan = scheduler._build_turn_plan(
        "组织多智能体完成企业知识库问答 MVP：前端、后端、测试和发布方案都要闭环，并给出最终可交付方案。"
    )

    assert [item["agent_id"] for item in plan] == ["frontend", "backend", "qa", "devops"]
    assert plan[2]["depends_on"] == ["frontend", "backend"]
    assert plan[3]["depends_on"] == ["frontend", "backend", "qa"]


@pytest.mark.asyncio
async def test_scheduler_agent_assigns_target_specific_plan_tasks():
    bus = EventDispatcher()
    blackboard = BlackboardManager(event_bus=bus)
    events: list[Event] = []
    bus.subscribe("*", lambda event: _append(events, event), target="*")
    scheduler = SchedulerAgent(
        session_id="sess_scheduler_target_tasks",
        agents={
            "frontend": AgentConfig(id="frontend", name="Frontend Worker", system_prompt="build ui", role="frontend"),
            "backend": AgentConfig(id="backend", name="Backend Worker", system_prompt="build api", role="backend"),
        },
        event_bus=bus,
        blackboard_mgr=blackboard,
        model_provider=None,
    )
    scheduler.current_task = "build frontend and backend"
    scheduler._turn_plan = scheduler._build_turn_plan(scheduler.current_task)

    await scheduler._assign(
        "backend",
        SchedulingDecision(
            decision_type="parallel",
            target_agent_id="frontend",
            target_agent_ids=["frontend", "backend"],
            task_description="generic implementation task",
        ),
    )

    assign = next(event for event in events if event.type == CONTROL_ASSIGN)
    assert assign.target == "backend"
    assert "Backend Worker" in assign.payload["task"]
    assert assign.payload["task"] == assign.payload["task_input"]["assigned_task"]
    assert assign.payload["task_input"]["scheduler_task"] == "generic implementation task"


@pytest.mark.asyncio
async def test_scheduler_agent_mentions_dispatch_once_then_complete():
    bus = EventDispatcher()
    blackboard = BlackboardManager(event_bus=bus)
    events: list[Event] = []
    bus.subscribe("*", lambda event: _append(events, event), target="*")
    scheduler = SchedulerAgent(
        session_id="sess_scheduler_mention",
        agents={
            "daily": AgentConfig(id="daily", name="Daily Chat Agent", system_prompt="chat"),
            "backend": AgentConfig(id="backend", name="Backend", system_prompt="build api"),
        },
        event_bus=bus,
        blackboard_mgr=blackboard,
        model_provider=None,
    )
    scheduler.start()

    await bus.publish(
        Event(
            type=USER_INPUT,
            payload={
                "content": "@Daily Chat Agent hello",
                "mention_target_agent_ids": ["daily"],
            },
            source="user",
        )
    )
    assign = await _wait_for(events, CONTROL_ASSIGN)

    await bus.publish(
        Event(
            type=AGENT_REPORT,
            payload={
                "agent_id": "daily",
                "task": "@Daily Chat Agent hello",
                "work_product": "hello",
                "report": {
                    "agent_id": "daily",
                    "state": "completed",
                    "will": "complete",
                    "confidence": 1.0,
                },
            },
            source="agent:daily",
        )
    )
    complete = await _wait_for(events, CONTROL_COMPLETE)
    await asyncio.sleep(0.05)
    await scheduler.stop()

    assignments = [event for event in events if event.type == CONTROL_ASSIGN]
    decisions = [event for event in events if event.type == SCHEDULER_DECISION]
    assert assign.target == "daily"
    assert len(assignments) == 1
    assert decisions[0].payload["decision"]["decision_type"] == "assign"
    assert decisions[-1].payload["decision"]["decision_type"] == "complete"
    assert complete.payload["reason"]


@pytest.mark.asyncio
async def test_scheduler_agent_uses_structured_mention_metadata():
    bus = EventDispatcher()
    blackboard = BlackboardManager(event_bus=bus)
    events: list[Event] = []
    bus.subscribe("*", lambda event: _append(events, event), target="*")
    scheduler = SchedulerAgent(
        session_id="sess_scheduler_structured_mention",
        agents={
            "daily": AgentConfig(id="daily", name="Daily Chat Agent", system_prompt="chat"),
            "deploy": AgentConfig(id="deploy", name="Deploy Agent", system_prompt="deploy"),
        },
        event_bus=bus,
        blackboard_mgr=blackboard,
        model_provider=None,
    )
    scheduler.start()

    await bus.publish(
        Event(
            type=USER_INPUT,
            payload={
                "content": "## Required Agent Mentions\n- @Deploy Agent (agent_id=deploy)\n\n你会干嘛",
                "context_metadata": {
                    "mention_target_agent_ids": ["deploy"],
                    "agent_mentions": [{"agent_id": "deploy", "agent_name": "Deploy Agent"}],
                },
            },
            source="user",
        )
    )
    assign = await _wait_for(events, CONTROL_ASSIGN)

    await bus.publish(
        Event(
            type=AGENT_REPORT,
            payload={
                "agent_id": "deploy",
                "task": "你会干嘛",
                "work_product": "deploy answer",
                "report": {
                    "agent_id": "deploy",
                    "state": "completed",
                    "will": "complete",
                    "confidence": 1.0,
                },
            },
            source="agent:deploy",
        )
    )
    await _wait_for(events, CONTROL_COMPLETE)
    await asyncio.sleep(0.05)
    await scheduler.stop()

    assignments = [event for event in events if event.type == CONTROL_ASSIGN]
    decisions = [event for event in events if event.type == SCHEDULER_DECISION]
    assert assign.target == "deploy"
    assert len(assignments) == 1
    assert decisions[0].payload["decision"]["target_agent_id"] == "deploy"
    assert decisions[-1].payload["decision"]["decision_type"] == "complete"


def test_scheduler_agent_name_matching_ignores_generic_agent_token():
    bus = EventDispatcher()
    scheduler = SchedulerAgent(
        session_id="sess_scheduler_matching",
        agents={
            "daily": AgentConfig(id="daily", name="Daily Chat Agent", system_prompt="chat"),
            "deploy": AgentConfig(id="deploy", name="Deploy Agent", system_prompt="deploy"),
        },
        event_bus=bus,
        blackboard_mgr=BlackboardManager(event_bus=bus),
        model_provider=None,
    )

    assert scheduler._agent_ids_mentioned_in("@Deploy Agent 你会干嘛") == ["deploy"]


def test_scheduler_agent_repair_keeps_decision_inside_mention_scope():
    bus = EventDispatcher()
    scheduler = SchedulerAgent(
        session_id="sess_scheduler_mention_repair",
        agents={
            "daily": AgentConfig(id="daily", name="Daily Chat Agent", system_prompt="chat"),
            "deploy": AgentConfig(id="deploy", name="Deploy Agent", system_prompt="deploy"),
            "frontend": AgentConfig(id="frontend", name="Frontend Worker", system_prompt="frontend"),
        },
        event_bus=bus,
        blackboard_mgr=BlackboardManager(event_bus=bus),
        model_provider=None,
    )
    scheduler.current_task = "@Deploy Agent hello"
    scheduler._mention_target_ids = ["deploy"]

    repaired = scheduler._repair_decision(
        SchedulingDecision(
            decision_type="parallel",
            target_agent_id="daily",
            target_agent_ids=["daily", "frontend"],
            verification_agents=["deploy"],
            task_description="hello",
        ),
        reports=[],
    )

    assert repaired.decision_type == "assign"
    assert repaired.target_agent_id == "deploy"
    assert repaired.target_agent_ids == ["deploy"]


@pytest.mark.asyncio
async def test_agent_loop_forces_artifact_tool_when_model_only_returns_text():
    events: list[Event] = []
    executor = FakeToolExecutor()
    loop = AgentLoop(
        AgentConfig(
            id="daily",
            name="Daily Chat Agent",
            system_prompt="You can create artifacts.",
            role="chat",
            tools=["artifact.create_pdf"],
        ),
        FakeModelProvider(),
        use_streaming=False,
    )

    result = await loop.run(
        "生成示例pdf预览卡片",
        {},
        tool_executor=executor,
        emit_event=lambda event: _append(events, event),
    )

    assert executor.calls
    assert executor.calls[0].tool_name == "artifact.create_pdf"
    tool_result = next(event for event in events if event.type == "agent.tool_result")
    assert tool_result.payload["result"]["output"]["artifact_id"] == "artifact-1"
    assert result["work_product"]


async def _append(target: list[Event], event: Event) -> None:
    target.append(event)


def test_fullstack_delivery_plan_is_dependency_ordered():
    scheduler = SchedulerAgent(
        session_id="sess_fullstack_plan",
        agents={
            "backend": AgentConfig(
                id="backend",
                name="Backend Worker",
                system_prompt="build api",
                role="backend",
                tools=["file.write", "sandbox.run", "api.test"],
            ),
            "frontend": AgentConfig(
                id="frontend",
                name="Frontend Worker",
                system_prompt="build ui",
                role="frontend",
                tools=["artifact.create_web_app", "file.write"],
            ),
            "daily": AgentConfig(
                id="daily",
                name="Daily Chat Agent",
                system_prompt="chat",
                role="chat",
                tools=["artifact.create_pdf", "artifact.create_docx", "artifact.create_html"],
            ),
            "reviewer": AgentConfig(
                id="reviewer",
                name="Reviewer",
                system_prompt="review",
                role="reviewer",
                tools=["test.run"],
            ),
        },
        event_bus=EventDispatcher(),
        blackboard_mgr=BlackboardManager(),
        model_provider=None,
    )
    task = "生成一个五子棋项目，包含前端后端，pdf说明文档"
    scheduler.current_task = task

    plan = scheduler._build_turn_plan(task)
    by_agent = {item["agent_id"]: item for item in plan}

    assert [item["agent_id"] for item in plan] == ["backend", "frontend", "daily", "reviewer"]
    assert by_agent["backend"]["stage"] == 1
    assert by_agent["frontend"]["depends_on"] == ["backend"]
    assert by_agent["daily"]["depends_on"] == ["backend", "frontend"]
    assert by_agent["reviewer"]["depends_on"] == ["backend", "frontend", "daily"]
    assert "后端" in by_agent["backend"]["assigned_task"]
    assert "HTML/Web" in by_agent["frontend"]["assigned_task"]
    assert "PDF" in by_agent["daily"]["assigned_task"]


def test_backend_data_app_plan_waits_for_backend_before_frontend():
    scheduler = SchedulerAgent(
        session_id="sess_backend_first_plan",
        agents={
            "backend": AgentConfig(
                id="backend",
                name="Backend Worker",
                system_prompt="build api",
                role="backend",
                tools=["file.write", "sandbox.run", "api.test"],
            ),
            "frontend": AgentConfig(
                id="frontend",
                name="Frontend Worker",
                system_prompt="build ui",
                role="frontend",
                tools=["artifact.create_web_app", "file.write"],
            ),
            "deploy": AgentConfig(
                id="deploy",
                name="Deploy Agent",
                system_prompt="deploy",
                role="deploy",
                tools=["deploy.preview"],
            ),
        },
        event_bus=EventDispatcher(),
        blackboard_mgr=BlackboardManager(),
        model_provider=None,
    )
    task = "生成五子棋应用，后端储存用户数据"
    scheduler.current_task = task

    plan = scheduler._build_turn_plan(task)
    by_agent = {item["agent_id"]: item for item in plan}

    assert [item["agent_id"] for item in plan] == ["backend", "frontend"]
    assert by_agent["backend"]["stage"] == 1
    assert by_agent["frontend"]["stage"] == 2
    assert by_agent["frontend"]["depends_on"] == ["backend"]
    scheduler._turn_plan = plan
    assert scheduler._ready_plan_targets() == ["backend"]


def test_fullstack_agent_tasks_follow_user_requirement_not_game_template():
    scheduler = SchedulerAgent(
        session_id="sess_generic_fullstack_plan",
        agents={
            "backend": AgentConfig(
                id="backend",
                name="Backend Worker",
                system_prompt="build api",
                role="backend",
                tools=["file.write", "sandbox.run", "api.test"],
            ),
            "frontend": AgentConfig(
                id="frontend",
                name="Frontend Worker",
                system_prompt="build ui",
                role="frontend",
                tools=["artifact.create_web_app", "file.write"],
            ),
            "deploy": AgentConfig(
                id="deploy",
                name="Deploy Agent",
                system_prompt="deploy",
                role="deploy",
                tools=["deploy.preview"],
            ),
        },
        event_bus=EventDispatcher(),
        blackboard_mgr=BlackboardManager(),
        model_provider=None,
    )
    task = "生成数据库管理应用，后端储存用户数据，前端根据后端 api 做出来精美页面，然后最后部署"
    scheduler.current_task = task

    plan = scheduler._build_turn_plan(task)
    by_agent = {item["agent_id"]: item for item in plan}

    assert [item["agent_id"] for item in plan] == ["backend", "frontend", "deploy"]
    assert by_agent["backend"]["stage"] == 1
    assert by_agent["frontend"]["stage"] == 2
    assert by_agent["deploy"]["stage"] == 5
    assert by_agent["frontend"]["depends_on"] == ["backend"]
    assert "数据库管理应用" in by_agent["backend"]["assigned_task"]
    assert "数据库管理应用" in by_agent["frontend"]["assigned_task"]
    assert "五子棋" not in by_agent["backend"]["assigned_task"]
    assert "五子棋" not in by_agent["frontend"]["assigned_task"]


@pytest.mark.asyncio
async def test_tech_lead_scheduler_receives_turn_plan_context(monkeypatch):
    captured: dict[str, str] = {}

    async def fake_collect_chat_stream(_provider, *, messages, system_prompt, temperature):
        captured["system_prompt"] = system_prompt
        captured["user_prompt"] = messages[0].content
        captured["temperature"] = str(temperature)
        return ChatResponse(
            content='{"decision_type":"assign","target_agent_id":"backend","target_agent_ids":["backend"],"task_description":"先完成后端数据接口","rationale":"按计划先做依赖项"}'
        )

    monkeypatch.setattr(
        "agent_runtime.strategies.tech_lead.collect_chat_stream",
        fake_collect_chat_stream,
    )
    scheduler = TechLeadScheduler(
        agents={
            "backend": AgentConfig(id="backend", name="Backend Worker", system_prompt="build api", role="backend"),
            "frontend": AgentConfig(id="frontend", name="Frontend Worker", system_prompt="build ui", role="frontend"),
        },
        model_provider=object(),
    )

    decision = await scheduler.make_decision(
        {},
        [
            _ready_report("backend"),
            _ready_report("frontend"),
        ],
        {
            "round": 1,
            "session_id": "sess",
            "current_task": "生成五子棋应用，后端储存用户数据",
            "turn_plan": [
                {"agent_id": "backend", "stage": 1, "depends_on": []},
                {"agent_id": "frontend", "stage": 2, "depends_on": ["backend"]},
            ],
        },
    )

    assert decision.target_agent_ids == ["backend"]
    assert "turn_plan" in captured["user_prompt"]
    assert "backend_before_frontend_for_data_apps" in captured["user_prompt"]
    assert "documentation should be" in captured["system_prompt"]


async def _wait_for(events: list[Event], event_type: str) -> Event:
    for _ in range(50):
        for event in events:
            if event.type == event_type:
                return event
        await asyncio.sleep(0.02)
    raise AssertionError(f"event {event_type} was not published")


def _completed_report(agent_id: str):
    from agent_runtime.core.types import AgentReport, AgentState, AgentWill

    return AgentReport(
        agent_id=agent_id,
        state=AgentState.COMPLETED,
        will=AgentWill.COMPLETE,
        confidence=1.0,
    )


def _ready_report(agent_id: str):
    from agent_runtime.core.types import AgentReport, AgentState, AgentWill

    return AgentReport(
        agent_id=agent_id,
        state=AgentState.READY,
        will=AgentWill.EXECUTE,
        confidence=1.0,
    )


class FakeModelProvider:
    async def chat(self, **_kwargs):
        return ChatResponse(content="li", tool_calls=None)

    async def chat_stream(self, **_kwargs):
        from model_provider import StreamChunk

        yield StreamChunk(content="li", finish_reason="stop")


class FakeToolExecutor:
    def __init__(self) -> None:
        self.calls = []

    async def list_tools(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": "artifact.create_pdf",
                    "description": "Create PDF",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]

    async def execute(self, tool_call):
        self.calls.append(tool_call)
        return {
            "type": "tool",
            "tool_name": tool_call.tool_name,
            "status": "succeeded",
            "output": {
                "artifact_id": "artifact-1",
                "artifact": {"conversationId": "conv-1", "title": "示例 PDF"},
                "preview_message_id": "preview-1",
            },
        }
