# 2026-06-05 异步多 Agent Runtime 收口说明

本文件记录 `docs-capability-completion` 分支本轮对多智能体运行时的真实落地范围，避免把仍属于长期路线的内容写成已完整交付。

## 已完成

- `agent_runtime.core.protocol` 已定义 `control.assign/pause/resume/cancel/complete/shutdown`、`agent.report/state_changed/failed`、`scheduler.decision`、`blackboard.updated` 等事件协议。
- `runtime.event_dispatcher.EventDispatcher` 支持 `publish()`、`subscribe()`、通配符过滤和 target 定向路由，同时保留旧 sink dispatch 兼容。
- `runtime.mailbox.Mailbox` 为 Agent / Scheduler 提供 `asyncio.Queue` inbox，可订阅 EventBus 的定向控制事件。
- `runtime.agent_stepper.AgentStepper` 兼容旧 `AgentLoop.run()`，并在每次 `emit_event` 后执行控制 checkpoint；`pause/resume/cancel/complete` 可以在 token/tool/status 等 step 间生效。
- `runtime.agent_actor.AgentActor` 作为独立 `asyncio.Task` 运行，收到 `control.assign` 后执行 AgentLoop，发布 `agent.state_changed`、`agent.report`、`agent.failed`，并把普通结果写入 Blackboard `agent_work`。
- `AgentActor` 收到 `control.complete` 后会发布 completed report 并退出；被 `control.cancel/complete` 中断的 assignment 会写入 Blackboard `agent_control`，便于审计和恢复。
- `strategies.scheduler_agent.SchedulerAgent` 已作为真实 `AgentActor`，订阅 `user.input`、`agent.report`、`blackboard.updated`、`agent.failed`，复用 `TechLeadScheduler` 的 LLM 调度能力，失败时降级到规则 fallback 并写入 `fallback_reason`，发布包含 `action/target_agent_ids/task/expected_outputs/requires_review` 的 `scheduler.decision` / `control.*`。
- `runtime.actor_orchestrator.ActorOrchestrator` 是普通群聊默认“自动组织”运行入口；`Session` 在 `scheduler_config.runtime == "actor"` 时启用该路径，workflow 画布保持兼容但必须由 `workflow_enabled=true` 显式启用。
- `ConversationSessionManager` 会持久化 actor runtime 事件到 `Conversation.extra.runtime`，前端可恢复调度决策、AgentRun 状态、输出摘要和取消原因；Session 复用会比较 `scheduling_strategy/runtime_mode/workflow_enabled`。

## 验证覆盖

- `backend/tests/test_agent_runtime/test_eventbus.py`：事件广播、通配订阅和 target routing。
- `backend/tests/test_agent_runtime/test_agent_stepper.py`：step 间 `cancel` 打断、`pause/resume` 等待恢复。
- `backend/tests/test_agent_runtime/test_agent_actor.py`：assignment 执行、Blackboard 写入、`control.complete` 收敛退出。
- `backend/tests/test_agent_runtime/test_scheduler_agent.py`：SchedulerAgent 继承 Actor 并把用户输入转成控制指令。
- `backend/tests/test_agent_runtime/test_actor_orchestrator.py`：actor runtime session 端到端运行。
- `backend/tests/test_conversation_session_manager.py`：generation 运行记录、取消事件和恢复数据。
- `frontend/src/lib/runtimeEvents.test.ts`、`frontend/src/lib/runningConversations.test.ts`：前端 runtime 状态折叠和左侧 running 状态清理。

## 当前边界

- 普通群聊默认使用 `tech_lead + actor` 自动组织；`WorkflowEngine` 只在当前会话显式启用画布后作为事实来源执行。
- Step checkpoint 依赖 AgentLoop 发出事件；如果底层模型调用长时间无增量事件，取消会在下一次 checkpoint 收敛，不是操作系统级强抢占。
- 跨进程 Blackboard、分布式 Agent 私有上下文同步、远程容器沙箱、企业级审批流仍是长期架构项。
