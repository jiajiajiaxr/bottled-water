# 功能使用说明

本文按产品功能说明 AgentHub 的使用方式和闭环目标。根目录 README 更偏架构概览，本文更偏实际操作和功能边界。

## 1. 登录与用户设置

用户可以注册新账号、使用已有账号登录，也可以走演示用户进入系统。

进入后可以在全局设置里维护用户基础信息、密码和模型配置。模型 API Key 只在后端读取，前端不保存真实密钥。

相关代码：

- 前端入口：`frontend/src/router/`、`frontend/src/features/settings/components/GlobalSettingsDrawer/`
- 前端 API：`frontend/src/api/`
- 后端 API：`backend/src/app/api/auth.py`
- 密码与 token：`backend/src/app/core/security.py`
- 用户模型：`backend/src/db/models/users.py`
- 测试：`tests/test_auth.py`、`tests/test_auth_settings.py`

## 2. 工作区

工作区用于隔离会话、项目、Agent、Skill、MCP、工具和文件。不同工作区下的会话列表相互独立，避免一个项目里的上下文污染另一个项目。

主要能力：

- 创建、编辑、归档、克隆、删除工作区。
- 管理工作区成员。
- 管理项目文件、提示词模板和快捷命令。
- 按当前工作区筛选会话、Agent、Skill、MCP 和工具。

相关代码：

- 后端 API：`backend/src/app/api/workspaces.py`
- 数据模型：`Workspace`、`WorkspaceMember`、`Project`、`ProjectFile`、`PromptTemplate`、`ShortcutCommand`
- 前端状态：`frontend/src/store/`、`frontend/src/pages/WorkbenchPage/`
- 测试：`tests/test_workspace_security_deploy_task.py`

## 3. 会话与 IM 工作台

会话是 AgentHub 的主入口。左侧是会话列表，中间是聊天区，右侧产物预览只在点击产物卡片时打开。

主要能力：

- 新建单聊或群聊。
- 会话置顶、归档、删除、搜索、分类、备注。
- 分类使用下拉选择，避免手填造成同类名称不一致。
- 会话列表显示最后一条消息；任务运行时显示“正在回答”状态，完成后恢复最后消息摘要。
- 输入框支持 Enter 立即发送，用户消息先本地插入，再异步等待后端确认。
- 生成中可以停止响应。

相关代码：

- 前端主工作台：`frontend/src/pages/WorkbenchPage/Workbench.tsx`
- 会话 API：`backend/src/app/api/conversations.py`
- 消息 API：`backend/src/app/api/messages.py`
- 消息持久化：`Message`、`MessageVersion`
- 实时事件：`backend/src/app/services/realtime/event_bus.py`
- 输出清理：`backend/src/app/services/output_filter.py`
- 测试：`tests/test_conversation.py`、`tests/test_message.py`

## 4. 单聊 Agent

单聊时，系统会直接启动当前 Agent 的小循环，而不是固定由 Master 代替执行。

执行逻辑：

```text
用户消息
  -> 当前 Agent
  -> 读取 Agent 的 model_config_id
  -> 读取 Agent 的工具 / Skill / MCP 权限
  -> run_agentic_tool_loop
  -> 流式回复和可选产物
```

如果 Agent 没有工具、Skill、MCP 权限，它就是普通对话型 Agent。如果有权限，则可以进入类似 Claude Code 的短 Agentic Loop：分析输入、选择工具、执行、汇总结果。

相关代码：

- Agent 列表与编辑：`backend/src/app/api/agents.py`
- Agent 执行循环：`backend/src/app/services/agents/function_loop.py`、`backend/src/app/services/agents/tool_loop.py`
- 编排入口：`backend/src/app/services/runtime_service.py`、`backend/src/agent_runtime/`
- 运行记录：`backend/src/app/services/runtime/generation_records.py`
- 官方 Agent 种子：`backend/src/app/services/seed.py`
- 前端 Agent 广场：`frontend/src/features/agents/components/AgentDirectoryDrawer/`

## 5. 群聊与多 Agent 协作

群聊可以在 `workflow` 和 `tech_lead` 两种调度策略之间切换。默认群聊会生成并使用工作流画布，`tech_lead` 则走多智能体 V2 的 Team Leader 调度链路。Master Agent 不再是隐藏最高调度者，而是一个擅长规划、补全、总结的官方 Agent。

默认行为：

- 群聊创建后会生成默认并行工作流。
- 如果用户没有指定调度策略，且当前群聊有 `conversation.extra.workflow`，则按 `workflow` 策略执行。
- 如果会话或消息明确选择 `tech_lead`，则由 TechLeadScheduler 记录调度决策、AgentRun 和 watchdog 事件。
- 如果用户明确让 Agent 规划，具备权限的 Agent 可以生成或修改 workflow，后端 normalize 后写回当前会话。
- Agent 节点会真正调用对应 Agent 的小循环。

相关代码：

- 工作流保存：`backend/src/app/api/conversations.py`
- 工作流执行：`backend/src/app/services/workflows/engine.py`、`backend/src/app/services/workflows/nodes/`
- 调度策略解析：`backend/src/app/services/chat/scheduling.py`
- V2 Session 运行：`backend/src/app/services/conversation_session_manager.py`、`backend/src/app/services/runtime_service.py`
- 工作流类型：`frontend/src/types/`

WebSocket V2 运行时会在每次 generation 启动时写入 `conversation.extra.runtime.generations[]`。该记录保存本轮 prompt 摘要、模型配置、调度决策、watchdog 事件和每个 Agent 的运行状态，取消或失败也会落库，便于刷新后排查和后续做运行历史界面。
- 群聊设置与画布：`frontend/src/features/chat/components/drawers/ConversationSettingsDrawer.tsx`、`frontend/src/features/workflow/`

## 6. 工作流画布

画布支持轻量 Dify 风格节点：

- `start`
- `agent`
- `tool`
- `skill`
- `mcp`
- `condition`
- `loop`
- `review`
- `artifact`
- `end`

用户可以在群聊设置里添加节点、编辑节点标题、类型、Agent、工具名、条件表达式、循环次数，并保存到当前群聊。

运行后会产生 `WorkflowRun`，每个节点的运行状态保存到 `node_states`。其中：

- `condition` 节点记录命中分支。
- `loop` 节点记录最大循环次数和当前迭代。
- `agent` 节点记录 Agent 输出摘要。
- `tool` / `skill` / `mcp` 节点记录调用结果。
- 节点失败策略支持 `stop`、`retry`、`skip`，重试次数会写入 `retry_count`，跳过失败节点时下游可以继续执行。

相关代码：

- 后端保存与 normalize：`backend/src/app/api/conversations.py`
- 后端运行态：`backend/src/app/services/workflows/runtime.py`、`backend/src/app/services/workflows/scheduler.py`
- 前端画布编辑：`frontend/src/features/workflow/`
- 类型定义：`frontend/src/types/`
- 数据模型：`WorkflowRun`

## 7. 文件能力

上传文件后，文件会显示在输入框和聊天消息里。发送消息时，附件摘要会进入后端消息上下文，让模型能看到用户上传的内容。

工具层支持：

- `file.upload`
- `file.extract_text`
- `file.preview`
- `file.convert`
- `file.summarize`
- `file.embed`

支持格式：

- PDF：文本提取和预览入口。
- Word docx：读取和生成。
- Excel xlsx：读取和生成。
- PPT pptx：读取和生成。
- Markdown / HTML：解析、预览、导出。
- 图片：预留 OCR / 视觉模型入口。

相关代码：

- 文件 API：`backend/src/app/api/files.py`
- 兼容附件 API：`backend/src/app/api/artifacts.py`
- 文件保存：`backend/src/app/services/files/`
- 文件解析和生成：`backend/src/app/services/tools/builtins/file/`、`backend/src/app/services/files/`
- 前端上传与预览：`frontend/src/features/chat/`、`frontend/src/features/workspaceFiles/`
- 测试：`tests/test_tools_files.py`

## 8. 产物预览与导出

产物不是每次回复都强制生成。只有当任务需要生成文档、表格、PPT、HTML/Web App、PDF 等内容时，Agent 或工具层才创建产物。聊天区会出现产物卡片，用户点击卡片后右侧预览面板打开。

主要能力：

- 预览 HTML、Markdown、纯文本、结构化产物。
- 编辑产物内容并保存版本。
- Diff 对比当前版本与上一版。
- 导出 PDF、DOCX、XLSX、PPTX、HTML、Markdown、ZIP 等格式。
- 部署或本地预览类产物会记录部署状态。

相关代码：

- 产物 API：`backend/src/app/api/artifacts.py`
- 产物创建：`backend/src/app/services/artifacts.py`
- 导出实现：`backend/src/app/services/tools/builtins/artifact/export.py`
- 文件生成工具：`backend/src/app/services/tools/builtins/artifact/`、`backend/src/app/services/document_model/`
- 前端预览：`frontend/src/features/preview/components/PreviewPanel/`
- 测试：`tests/test_artifact.py`、`tests/test_deployment.py`

## 9. Agent 广场

Agent 广场包含官方 Agent 和用户自定义 Agent。

官方 Agent：

- Master Agent：任务理解、权限判断、规划、补全、聚合。
- Frontend Worker：前端页面、交互、UI、Web App 产物。
- Backend Worker：接口、数据模型、服务逻辑。
- Reviewer：审查、测试、安全、文档评审。
- Deploy Agent：导出、预览、部署、回滚。
- Writing Agent：写作、文档、PDF、DOCX、PPT。
- Daily Chat Agent：日常问答、附件摘要、上下文续聊。

用户可以：

- 创建 Agent。
- 使用 AI 创建 Agent。
- 编辑 Agent 名称、描述、底层模型、系统提示词、工具权限、Skill 权限、MCP 权限。
- 测试 Agent，前端会显示等待状态、失败状态和真实返回。
- 删除用户自定义 Agent。

相关代码：

- API：`backend/src/app/api/agents.py`
- 官方种子：`backend/src/app/services/seed.py`
- 工具箱：`backend/src/app/services/tools/toolboxes.py`
- Agent 执行：`backend/src/app/services/agents/function_loop.py`、`backend/src/app/services/agents/tool_loop.py`
- 前端：`frontend/src/features/agents/components/AgentDirectoryDrawer/`

## 10. 模型管理

全局设置里维护模型供应商和模型配置。系统默认支持火山方舟，也保留 OpenAI-compatible 结构。

关键点：

- `.env` 只从项目根目录读取。
- API Key 不进入前端。
- 模型测试走真实后端接口。
- 真实模型不可用时可以配置 mock 模式。

相关代码：

- 配置读取：`backend/src/app/core/config.py`
- 火山方舟适配：`backend/src/app/services/llm/ark.py`
- 模型测试：`backend/src/app/services/llm/gateway.py`
- 模型 API：`backend/src/app/api/models.py`
- 前端设置：`frontend/src/features/settings/components/GlobalSettingsDrawer/`

## 11. Skills

Skill 是 Agent 可选择的能力包，可以手动创建、AI 创建，也可以从 MCP 导入。

主要能力：

- 创建 Skill。
- AI 生成 Skill。
- 从 MCP 服务导入 Skill。
- 测试 Skill。
- 删除用户创建的 Skill。
- Agent 可以按权限绑定 Skill。
- Skill manifest 支持 `prompt_skill`、`agent_skill`、`mcp_skill`、`script_skill`。
- `script_skill` 不会裸跑代码，必须声明 `file.write` 和 `sandbox.run` 依赖，并通过工作区沙箱工具链执行。
- Skill manifest 每次更新都会保存前一版完整快照、hash、变更字段和操作者，便于恢复和审计。
- Skill 测试用例通过统一 `SkillRuntime` 执行，测试报告包含每个 case 的输入、断言、输出摘要、依赖检查结果和 `SkillRun` 记录。
- Skill 详情页或 API 的“测试 Skill”入口同样走 `SkillRuntime`，会按 manifest runtime 执行 `prompt_skill`、`agent_skill`、`mcp_skill`、`script_skill`，并写入 `SkillRun`，不会绕过权限、依赖和审计。
- Skill 依赖检查会从数据库 ToolDefinition、MCP Server、Skill 目录解析依赖；缺失、禁用、不可见都会返回明确原因。

相关代码：

- API：`backend/src/app/api/skills.py`
- Agent 选择 Skill：`backend/src/app/services/agents/tool_loop.py`、`backend/src/app/services/skills/`
- 前端管理：`frontend/src/features/platform/components/PlatformControlDrawer/`
- 测试：`tests/test_skills.py`

## 12. MCP 服务

MCP 服务用于接入外部工具和上下文服务。

主要能力：

- 注册 HTTP 或 stdio 类型 MCP。
- 导入 MCP 配置。
- 探测 MCP 工具。
- 调用 MCP 工具。
- 查看调用记录。
- 删除用户创建的 MCP 服务。
- Agent 可按权限绑定 MCP。
- HTTP / stdio MCP 探测会发起 JSON-RPC `tools/list`，并将结果写入服务工具目录；探测失败会在服务 metadata 中记录 `last_probe` 错误原因。
- 本地演示内置 `agenthub-mcp-filesystem` 适配器可在缺少外部二进制时降级为受控工具目录，便于演示文件类 MCP 能力。

相关代码：

- API：`backend/src/app/api/mcp.py`
- 运行时：`backend/src/app/services/mcp/`
- 调用记录模型：`McpToolInvocation`
- 前端管理：`frontend/src/features/platform/components/PlatformControlDrawer/`
- 测试：`tests/test_model_mcp_sandbox.py`

## 13. 工具目录

工具是 AgentHub 的执行边界。模型负责判断意图，后端工具负责真实执行。

工具来源：

- 内置工具：文件、产物、沙箱、浏览器预览、数据库检查、API 测试、安全审计、部署预览等。
- 自定义工具：用户创建的工具定义。
- AI 生成工具：由模型生成受限 Python 片段，保存到工具工作区后可调用。

用户可以：

- 查看工具目录。
- 创建自定义工具。
- AI 生成工具。
- 测试工具调用。
- 删除自定义工具。
- 给 Agent 授权工具。

相关代码：

- 工具 API：`backend/src/app/api/tools.py`
- 工具注册与调用：`backend/src/app/services/tools/catalog.py`、`backend/src/app/services/tools/executor.py`
- 自定义工具存放：`var/ai-tools/generated`
- 前端管理：`frontend/src/features/platform/components/PlatformControlDrawer/`
- 测试：`tests/test_tools_files.py`

## 14. 沙箱、远程控制与部署

沙箱和远程控制用于承载高权限执行，当前主要用于演示和受限命令执行链。

主要能力：

- 创建沙箱会话。
- 执行受限命令。
- 记录命令结果。
- 创建远程连接配置。
- 连接、检查和删除远程连接。
- 产物部署预览、健康检查、回滚记录和审计。
- 未启用容器/云部署运行时时，返回明确失败原因，不伪造生产发布成功。

相关代码：

- 沙箱 API：`backend/src/app/api/sandbox.py`
- 部署 API：`backend/src/app/api/deployments.py`
- 部署服务：`backend/src/app/services/deployments.py`
- 数据模型：`SandboxSession`、`RemoteConnection`、`Deployment`
- 前端入口：`frontend/src/features/platform/components/PlatformControlDrawer/`
- 测试：`tests/test_workspace_security_deploy_task.py`、`tests/test_deployment.py`

## 15. 后台任务

后台任务用于长任务和异步生成。顶部任务按钮可以查看当前进行中的任务，也可以创建后台任务。左侧会话列表会同步显示正在回答状态。

相关代码：

- 队列：`backend/src/app/services/queue.py`
- 编排入口：`backend/src/app/services/runtime_service.py`、`backend/src/agent_runtime/`
- 前端组件：`frontend/src/features/chat/`、`frontend/src/hooks/useBackgroundTaskPolling.ts`
- 测试：`tests/test_workspace_security_deploy_task.py`

## 16. 权限与审计

平台保留 RBAC、权限和审计日志能力，用于管理高风险操作。

主要能力：

- 角色、权限、用户列表。
- 在平台控制台直接更新用户角色。
- 审计日志记录与详情展开。
- 高权限操作落审计。
- 工具、MCP、沙箱、远程连接等敏感能力由后端统一控制。

相关代码：

- 审计服务：`backend/src/app/services/audit.py`
- 安全 API：`backend/src/app/api/security_ops.py`
- 数据模型：`Role`、`Permission`、`UserRole`、`RolePermission`、`AuditLog`
- 前端入口：`frontend/src/features/platform/components/SecurityOpsPanel.tsx`、`frontend/src/features/settings/`

用户角色更新会同时写入 `users.role` 和 `user_roles` 关系表。系统默认保留 `ROLE_USER`，当用户被提升为 developer/admin 等角色时，会追加对应角色关系，并记录 `security.user.role.update` 审计事件。前端角色下拉会调用同一后端接口，更新后刷新用户列表和审计数据。


### MCP 调用失败与诊断语义

- MCP 工具调用会先写入 `McpToolInvocation`，再执行 allowlist、schema 和 transport 检查，成功或失败都会留下审计记录。
- `error_code` 目前包含 `mcp_tool_not_allowed`、`mcp_argument_validation_failed`、`mcp_timeout`、`mcp_authentication_failed`、`mcp_transport_unsupported`、`mcp_transport_error`，前端可以据此展示明确提示。
- `server.tools` 中显式禁用的工具优先级高于 `tool_filter` 通配符；被拒绝的调用不会触发真实 transport。
- HTTP MCP 会明确区分 timeout、request error 和 401/403 鉴权问题；SSE/WebSocket MCP 暂未启用真实 transport 时会返回可读降级错误，并保留原文件/配置下载与调用记录。
- MCP 服务探测和工具列表不再由路由硬编码默认工具；`/mcp-servers/{id}/probe` 复用 `services/mcp/discovery.py`，HTTP/stdio 优先真实 `tools/list`，失败时显示 `last_probe` 诊断。
