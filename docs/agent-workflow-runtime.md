# Agent 与工作流运行机制

本文说明 AgentHub 的核心运行时：Agentic Loop、默认自动组织群聊、显式启用的画布编排、工具权限、工作流运行态和产物生成。

## 1. 基本原则

AgentHub 不是“所有任务都交给 Master Agent”的集中式系统。当前原则是：

- 单聊：当前 Agent 自己执行，策略为 `single_agent`。
- 群聊：默认走 `tech_lead + actor` 自动组织链路；只有当前会话显式启用 `workflow_enabled=true` 时，才以画布 workflow 为事实来源。

补充：`tech_lead` 模式默认使用 Actor Runtime。会话配置
`conversation.extra.runtime_mode = "actor"` 后，Session 会启动事件驱动的
`ActorOrchestrator`：Team Leader 作为 `SchedulerAgent` 订阅 `user.input`、
`agent.report`、`blackboard.updated` 和 `agent.failed`，Worker 作为 `AgentActor` 接收
`control.assign/pause/resume/cancel/complete`。该路径会持续发布
`scheduler.decision`、`agent.state_changed`、`agent.report`，并把调度决策、
Agent 输出和错误写入 Blackboard。画布仍绑定 `conversation.extra.workflow`，但只有启用后才接管群聊执行。
- Master：只是擅长规划、补全、总结的官方 Agent。
- 权限：Agent 能做什么由自身配置决定。
- 工具：模型不直接修改世界，后端工具层负责真实执行。

## 2. 单聊运行时

单聊会话一般只有用户和一个 Agent。

```text
User message
  -> conversation participants
  -> selected Agent
  -> run_agentic_tool_loop(db, conversation, prompt, agent=agent)
  -> model reply
  -> optional tool / skill / mcp calls
  -> assistant message
```

关键文件：

- `backend/src/app/services/agents/direct.py`：单聊执行入口，创建 assistant 消息并发布 SSE 事件。
- `backend/src/app/services/agents/function_loop.py`：Agent Function Calling Loop，负责模型、工具调用、结果回填和最终回复。
- `backend/src/app/services/agents/tool_loop.py`：把 Agent 权限转换为 Tool / Skill / MCP function schema，并统一执行。
- `backend/src/app/services/tools/`：工具目录、权限、参数校验和执行记录。
- `backend/src/app/services/mcp/`：MCP server 目录、发现、transport 和调用记录。

## 3. Agentic Loop

Agentic Loop 是短循环，不追求无限自治，重点是演示和产品闭环稳定。

简化流程：

```text
收集上下文
  -> 读取 Agent 配置和权限
  -> 选择可用 Skill / MCP / Tool
  -> 调用模型生成回复或工具意图
  -> 执行已授权工具
  -> 汇总工具结果
  -> 产出最终回复和产物
```

权限来源：

- `Agent.config.tools`
- `Agent.config.skill_ids`
- `Agent.config.mcp_server_ids`
- `Agent.config.agentic_loop`

如果没有工具、Skill、MCP 权限，则只调用模型生成普通回复。

## 4. 群聊调度策略

消息入口和 WebSocket 入口统一通过 `backend/src/app/services/chat/scheduling.py` 解析调度策略。

优先级如下：

1. 单聊固定为 `single_agent`。
2. 消息级 `scheduling_strategy` 只在合法范围内作为本轮显式覆盖。
3. 会话级 `conversation.extra.scheduling_strategy`。
4. `conversation.extra.workflow_enabled === true` 时使用 `workflow`。
5. 其他群聊默认使用 `tech_lead`，并优先进入 `runtime_mode="actor"`。

`ConversationSessionManager` 复用 Session 时会同时比较模型配置、调度策略、`runtime_mode` 和 `workflow_enabled`；当用户从自动组织切换到画布执行或反向切换时，会重新创建对应策略的 `AgentSession`，避免旧调度器污染后续 generation。

## 5. 显式启用后的群聊画布编排

当 `conversation.extra.workflow_enabled=true` 时，群聊的事实来源是：

```text
conversation.extra.workflow
```

执行流程：

```text
User message
  -> load workflow
  -> sanitize workflow
  -> optional replan
  -> compute execution order from edges
  -> create WorkflowRun
  -> execute nodes
  -> persist node_states
  -> create final assistant message
```

如果 workflow 不存在，会根据当前群聊成员生成默认工作流。默认工作流不会强制走 Master，而是让所有参与 Agent 以默认编排参与。保存或自动生成 workflow 只更新草稿；用户关闭启用状态后，群聊会回到 `tech_lead + actor` 自动组织。

## 6. Agent 修改画布

当用户明确提出“让 Master 规划”“让某个 Agent 重新编排流程”“根据这些 Agent 自动生成工作流”等意图时，具备规划权限的 Agent 可以生成新的 workflow。

后端会做 normalize：

- 保留 `id`
- 保留 `title`
- 保留 `role`
- 保留 `status`
- 保留 `meta`
- 保留 `agent_id`
- 保留 `type`
- 保留 `config`
- 校验节点类型
- 校验边关系
- 补齐缺省字段

normalize 后的 workflow 会写回 `conversation.extra.workflow`，成为后续群聊执行的统一事实来源。

## 7. 节点类型

### start

入口节点，记录用户输入和附件摘要。

常见 config：

```json
{
  "input_types": ["text", "file"]
}
```

### agent

调用指定 Agent。

常见 config：

```json
{
  "agent_id": "agent-id"
}
```

执行时调用：

```python
run_agentic_tool_loop(..., agent=agent)
```

### tool

调用后端工具目录里的工具。

常见 config：

```json
{
  "tool_name": "artifact.create_docx",
  "arguments": {}
}
```

### skill

调用指定 Skill。

常见 config：

```json
{
  "skill_id": "skill-id"
}
```

### mcp

调用 MCP 服务工具。

常见 config：

```json
{
  "mcp_server_id": "server-id",
  "tool_name": "tool.name",
  "arguments": {}
}
```

### condition

条件节点。运行态会记录命中分支。

常见 config：

```json
{
  "expression": "input.includes('审查')"
}
```

运行态示例：

```json
{
  "matched_branch": "true"
}
```

### loop

循环节点。运行态会记录最大次数和当前次数。

常见 config：

```json
{
  "max_iterations": 3
}
```

运行态示例：

```json
{
  "max_iterations": 3,
  "current_iteration": 1
}
```

### review

审查节点，通常绑定 Reviewer 或具备审查能力的 Agent。

### artifact

产物节点，用于创建 PDF、DOCX、XLSX、PPTX、HTML、Web App 等真实产物。

执行语义：

- 根据 `config.tool_name` 或 `config.artifact_type / format / output_format` 映射到 `artifact.create_*`。
- 节点参数支持 `name`、`body`、`html`、`template`、`content_model` 和 `arguments`，所有字符串会经过工作流变量 resolver。
- 后端通过 `agents.tool_loop.execute_tool_by_name()` 进入统一工具层，执行结果写入 `tool_invocations`，并返回真实 `artifact_id`、`preview_url`、`export_url`、`format`、`filename`、`media_type`。
- 成功后发布 `artifact:created` 和预览卡片 `message:new`；失败时节点状态为 `failed`，错误写入 `node_states`。

### end

结束节点，汇总最终回复。

## 8. WorkflowRun

`WorkflowRun` 保存一次工作流运行快照。

主要字段：

- `conversation_id`
- `status`
- `workflow_snapshot`
- `node_states`
- `started_at`
- `completed_at`

`node_states` 中每个节点会包含：

- `id`
- `title`
- `type`
- `status`
- `progress`
- `message`
- `output`
- `retry_count`
- `started_at`
- `completed_at`

前端可以通过它展示每个节点是否运行、是否失败、输出是什么。

节点失败策略由 `config.failure_strategy` 或 `config.on_failure` 控制：

- `stop`：默认策略。节点失败后当前工作流失败，依赖它的下游节点会被跳过。
- `retry`：节点失败后重试。可用 `config.retry` 或 `config.retry_count` 指定重试次数，当前实现限制在 0-3 次；如果只写 `failure_strategy: "retry"`，默认重试 1 次。
- `skip`：节点失败后将该节点标记为 `skipped`，在 `output.reason` 写入 `failure_strategy_skip`，并允许下游继续运行。

每次重试会更新 `node_states[].retry_count`，并记录 `node.retry` 事件，便于刷新后恢复运行历史和排查失败原因。

## 9. 工具调用链

Agent 调用工具时走统一工具层：

```text
Agentic Loop
  -> select builtin/custom tool
  -> services.tools.executor.invoke_tool
  -> builtin handler or custom python
  -> result returned to Agent
  -> optional artifact/message/event
```

内置工具方向：

- 文件：`file.upload`、`file.extract_text`、`file.preview`、`file.convert`、`file.summarize`、`file.embed`
- 产物：`artifact.create_pdf`、`artifact.create_docx`、`artifact.create_xlsx`、`artifact.create_pptx`、`artifact.create_html`、`artifact.create_web_app`
- 审查：`artifact.diff`、`test.run`、`security.audit`、`document.review`
- 工程：`sandbox.run`、`browser.preview`、`db.inspect`、`api.test`
- 部署：`deploy.preview`、`deploy.rollback`

## 10. 产物生成链

用户说“生成 PDF 项目方案”时，理想链路是：

```text
Master / Planner 理解任务
  -> Writer 或 Document Agent 生成结构
  -> artifact.create_pdf 工具生成真实 PDF
  -> Reviewer 审查
  -> 聊天区出现产物卡片
  -> 用户点击卡片打开右侧预览
  -> 可编辑、Diff、导出
```

产物相关文件：

- `backend/src/app/services/tools/builtins/artifact/`
- `backend/src/app/services/document_model/`
- `backend/src/app/services/artifacts.py`
- `backend/src/app/api/artifacts.py`
- `frontend/src/features/preview/components/PreviewPanel`

## 11. 演示链路

一个完整演示可以按下面走：

1. 注册或演示登录。
2. 创建工作区。
3. 进入左侧会话栏，新建多 Agent 群聊。
4. 选择 Frontend Worker、Backend Worker、Reviewer、Deploy Agent 等成员。
5. 上传需求文件，确认附件显示在输入框。
6. 发送任务。
7. 左侧会话显示正在回答。
8. 群聊读取当前 workflow，按画布运行。
9. Agent 节点分别调用自己的 Agentic Loop。
10. 工具、Skill、MCP 按权限执行。
11. Reviewer 节点审查。
12. 如有真实产物，聊天区出现产物卡片。
13. 点击产物卡片，右侧预览打开。
14. 编辑产物、查看 Diff、导出文件。
15. 回到历史会话，确认消息和产物可恢复。

## 12. 运行时主链路收口

当前新业务统一走下面的链路：

```text
Frontend WebSocket / SSE compatibility
  -> ConversationSessionManager
  -> OrchestratorService.create_session()
  -> agent_runtime.AgentSession
  -> Scheduler / AgentActor / Workflow runtime
  -> app services ToolExecutor adapter
  -> ToolInvocation + Artifact + Message
  -> RuntimeEvent -> WebSocket/SSE sink
```

关键边界：

- WebSocket 是首选实时通道；SSE 仅是兼容入口，但也委托给同一个 SessionManager。
- `message_stop` 表示某条 Agent 消息结束；不能关闭整个 generation。
- `system.session_completed` / `generation_finished` / `generation:cancelled` / `generation:failed` 才是全局终态。
- `workflow:completed` 只表示画布运行态完成，前端需等待 generation 终态再清理会话 running。
- 工具成功不直接刷系统消息；成功工具记录进入 ToolInvocation、运行日志和消息底部摘要。Artifact 工具成功后由后端创建真实 preview_card。

旧入口边界：

- `services/chat/orchestrator.py`、`services/agents/direct.py`、`services/agents/function_loop.py` 只保留旧 API、测试和兼容调用所需 shim。
- 新增业务应接入 `agent_runtime`、`ConversationSessionManager`、`services/tools/*`、`services/artifacts/*`，不要继续扩展旧 orchestrator 或旧 tool registry。

