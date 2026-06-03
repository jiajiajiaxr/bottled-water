# 功能使用说明

本文按产品功能说明 AgentHub 的使用方式和闭环目标。根目录 README 更偏架构概览，本文更偏实际操作和功能边界。

## 1. 登录与用户设置

用户可以注册新账号、使用已有账号登录，也可以走演示用户进入系统。

进入后可以在全局设置里维护用户基础信息、密码和模型配置。模型 API Key 只在后端读取，前端不保存真实密钥。

相关代码：

- 前端入口：`frontend/src/App.tsx`
- 前端 API：`frontend/src/api.ts`
- 后端 API：`backend/app/api/auth.py`
- 密码与 token：`backend/app/core/security.py`
- 用户模型：`backend/db/models/users.py`
- 测试：`tests/test_auth.py`、`tests/test_auth_settings.py`

## 2. 工作区

工作区用于隔离会话、项目、Agent、Skill、MCP、工具和文件。不同工作区下的会话列表相互独立，避免一个项目里的上下文污染另一个项目。

主要能力：

- 创建、编辑、归档、克隆、删除工作区。
- 管理工作区成员。
- 管理项目文件、提示词模板和快捷命令。
- 按当前工作区筛选会话、Agent、Skill、MCP 和工具。

相关代码：

- 后端 API：`backend/app/api/workspaces.py`
- 数据模型：`Workspace`、`WorkspaceMember`、`Project`、`ProjectFile`、`PromptTemplate`、`ShortcutCommand`
- 前端状态：`frontend/src/App.tsx` 中的 `workspaces`、`activeWorkspaceId`
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

- 前端主工作台：`frontend/src/App.tsx` 中的 `Workbench`
- 会话 API：`backend/app/api/conversations.py`
- 消息 API：`backend/app/api/messages.py`
- 消息持久化：`Message`、`MessageVersion`
- 实时事件：`backend/app/services/events.py`
- 输出清理：`backend/app/services/output_filter.py`
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

- Agent 列表与编辑：`backend/app/api/agents.py`
- Agent 执行循环：`backend/app/services/agentic_runtime.py`
- 编排入口：`backend/app/services/runtime_service.py`、`backend/agent_runtime/`
- 官方 Agent 种子：`backend/app/services/seed.py`
- 前端 Agent 广场：`frontend/src/App.tsx` 中的 `AgentDirectoryDrawer`

## 5. 群聊与多 Agent 协作

群聊以工作流画布为事实来源。Master Agent 不再是隐藏最高调度者，而是一个擅长规划、补全、总结的官方 Agent。

默认行为：

- 群聊创建后会生成默认并行工作流。
- 如果用户没有要求重新规划，则按 `conversation.extra.workflow` 执行。
- 如果用户明确让 Agent 规划，具备权限的 Agent 可以生成或修改 workflow，后端 normalize 后写回当前会话。
- Agent 节点会真正调用对应 Agent 的小循环。

相关代码：

- 工作流保存：`backend/app/api/conversations.py`
- 工作流执行：`backend/app/services/runtime_service.py`、`backend/agent_runtime/`
- 工作流类型：`frontend/src/types.ts`
- 群聊设置与画布：`frontend/src/App.tsx` 中的 `ConversationSettingsDrawer`

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

相关代码：

- 后端保存与 normalize：`backend/app/api/conversations.py`
- 后端运行态：`backend/app/services/runtime_service.py`、`backend/agent_runtime/`
- 前端画布编辑：`frontend/src/App.tsx`
- 类型定义：`frontend/src/types.ts`
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

- 文件 API：`backend/app/api/files.py`
- 兼容附件 API：`backend/app/api/artifacts.py`
- 文件保存：`backend/app/services/files.py`
- 文件解析和生成：`backend/app/services/file_tools.py`
- 前端上传与预览：`frontend/src/App.tsx` 中的 `uploadFile`、附件渲染逻辑
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

- 产物 API：`backend/app/api/artifacts.py`
- 产物创建：`backend/app/services/artifacts.py`
- 导出实现：`backend/app/services/artifact_exports.py`
- 文件生成工具：`backend/app/services/file_tools.py`
- 前端预览：`frontend/src/App.tsx` 中的 `PreviewPanel`
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

- API：`backend/app/api/agents.py`
- 官方种子：`backend/app/services/seed.py`
- 工具箱：`backend/app/services/tool_registry.py`
- Agent 执行：`backend/app/services/agentic_runtime.py`
- 前端：`frontend/src/App.tsx` 中的 `AgentDirectoryDrawer`

## 10. 模型管理

全局设置里维护模型供应商和模型配置。系统默认支持火山方舟，也保留 OpenAI-compatible 结构。

关键点：

- `.env` 只从项目根目录读取。
- API Key 不进入前端。
- 模型测试走真实后端接口。
- 真实模型不可用时可以配置 mock 模式。

相关代码：

- 配置读取：`backend/app/core/config.py`
- 火山方舟适配：`backend/app/services/ark.py`
- 模型测试：`backend/app/services/llm_gateway.py`
- 模型 API：`backend/app/api/models.py`
- 前端设置：`frontend/src/App.tsx` 中的 `GlobalSettingsDrawer`

## 11. Skills

Skill 是 Agent 可选择的能力包，可以手动创建、AI 创建，也可以从 MCP 导入。

主要能力：

- 创建 Skill。
- AI 生成 Skill。
- 从 MCP 服务导入 Skill。
- 测试 Skill。
- 删除用户创建的 Skill。
- Agent 可以按权限绑定 Skill。

相关代码：

- API：`backend/app/api/skills.py`
- Agent 选择 Skill：`backend/app/services/agentic_runtime.py`
- 前端管理：`frontend/src/App.tsx` 中全局设置的 `Skills` 页签
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

相关代码：

- API：`backend/app/api/mcp.py`
- 运行时：`backend/app/services/mcp_runtime.py`
- 调用记录模型：`McpToolInvocation`
- 前端管理：`frontend/src/App.tsx` 中全局设置的 `MCP` 页签
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

- 工具 API：`backend/app/api/tools.py`
- 工具注册与调用：`backend/app/services/tool_registry.py`
- 自定义工具存放：`var/ai-tools/generated`
- 前端管理：`frontend/src/App.tsx` 中全局设置的 `Tools` 页签
- 测试：`tests/test_tools_files.py`

## 14. 沙箱、远程控制与部署

沙箱和远程控制用于承载高权限执行，当前主要用于演示和受限命令执行链。

主要能力：

- 创建沙箱会话。
- 执行受限命令。
- 记录命令结果。
- 创建远程连接配置。
- 连接、检查和删除远程连接。
- 产物部署预览和回滚记录。

相关代码：

- 沙箱 API：`backend/app/api/sandbox.py`
- 部署 API：`backend/app/api/deployments.py`
- 数据模型：`SandboxSession`、`RemoteConnection`、`Deployment`
- 前端入口：`frontend/src/App.tsx` 中的 `PlatformControlDrawer`
- 测试：`tests/test_workspace_security_deploy_task.py`、`tests/test_deployment.py`

## 15. 后台任务

后台任务用于长任务和异步生成。顶部任务按钮可以查看当前进行中的任务，也可以创建后台任务。左侧会话列表会同步显示正在回答状态。

相关代码：

- 队列：`backend/app/services/queue.py`
- 编排入口：`backend/app/services/runtime_service.py`、`backend/agent_runtime/`
- 前端组件：`frontend/src/App.tsx` 中的 `BackgroundTasksButton`
- 测试：`tests/test_workspace_security_deploy_task.py`

## 16. 权限与审计

平台保留 RBAC、权限和审计日志能力，用于管理高风险操作。

主要能力：

- 角色、权限、用户列表。
- 审计日志记录。
- 高权限操作落审计。
- 工具、MCP、沙箱、远程连接等敏感能力由后端统一控制。

相关代码：

- 审计服务：`backend/app/services/audit.py`
- 安全 API：`backend/app/api/security_ops.py`
- 数据模型：`Role`、`Permission`、`UserRole`、`RolePermission`、`AuditLog`
- 前端入口：`frontend/src/App.tsx` 中平台控制和全局设置相关面板

