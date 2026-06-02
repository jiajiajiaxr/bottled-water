# Agent 与工作流运行机制

本文说明 AgentHub 的核心运行时：Agentic Loop、画布优先群聊编排、工具权限、工作流运行态和产物生成。

## 1. 基本原则

AgentHub 不是“所有任务都交给 Master Agent”的集中式系统。当前原则是：

- 单聊：当前 Agent 自己执行。
- 群聊：当前会话的 workflow 先执行。
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

- `backend/app/services/orchestrator.py`：判断会话类型，选择单聊或群聊路径。
- `backend/app/services/agentic_runtime.py`：执行 Agent 的小循环。
- `backend/app/services/tool_registry.py`：执行工具。
- `backend/app/services/mcp_runtime.py`：执行 MCP。

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

## 4. 群聊画布优先编排

群聊的事实来源是：

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

如果 workflow 不存在，会根据当前群聊成员生成默认工作流。默认工作流不会强制走 Master，而是让所有参与 Agent 以默认编排参与。

## 5. Agent 修改画布

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

## 6. 节点类型

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

### end

结束节点，汇总最终回复。

## 7. WorkflowRun

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
- `started_at`
- `completed_at`

前端可以通过它展示每个节点是否运行、是否失败、输出是什么。

## 8. 工具调用链

Agent 调用工具时走统一工具层：

```text
Agentic Loop
  -> select builtin/custom tool
  -> tool_registry.invoke_tool
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

## 9. 产物生成链

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

- `backend/app/services/file_tools.py`
- `backend/app/services/artifacts.py`
- `backend/app/services/artifact_exports.py`
- `backend/app/api/artifacts.py`
- `frontend/src/App.tsx` 中的 `PreviewPanel`

## 10. 演示链路

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

