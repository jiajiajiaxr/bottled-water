# AgentHub 实现状态与文档承诺审计

本文用于把 README 和 docs 中的产品承诺映射到当前代码实现，区分已完成、已实现但仍需加固、未完整实现和长期架构计划。它不是 roadmap 口号，而是维护时判断“文档是否说过头”的依据。

## 审计范围

本轮审计覆盖：

- `README.md`
- `docs/functional-guide.md`
- `docs/agent-workflow-runtime.md`
- `docs/backend-architecture.md`
- `docs/capability-data-boundaries.md`
- `docs/capability-module-migration.md`
- `docs/architecture/multi-agent-v2-design.md`
- `docs/多智能体运行时架构改进方案.md`
- `docs/多智能体运行时异步架构改造实施计划.md`
- `docs/多智能体聊天应用架构设计总结.md`

状态说明：

- **已完成**：主链路已落到当前代码，且有测试或运行路径覆盖。
- **已实现，需持续加固**：功能可用，但仍依赖兼容层、环境能力或部分降级。
- **部分完成**：已有模块或接口，尚未覆盖完整承诺。
- **Roadmap**：属于架构设计或长期演进，不应在产品说明中表述为已完整交付。

## 文档承诺对照表

| 文档承诺 | 当前代码位置 | 状态 | 缺口 / 说明 | 优先级 |
| --- | --- | --- | --- | --- |
| Tool 目录统一展示内置和自定义工具，Agent Function Calling 暴露与执行一致 | `backend/src/app/services/tools/catalog.py`、`executor.py`、`builtins/`、`backend/src/app/services/agents/tool_loop.py`、`backend/src/app/api/tools.py` | 已完成 | 本轮已将 `/api/v1/tools`、seed 和旧 `agentic_runtime.py` 收敛到新版 catalog/executor；顶层 `tool_registry.py` 仅保留 shim。 | P0 |
| 内置 Tool 同步到 `tool_definitions`，目录去重，执行写入 `tool_invocations` | `services/tools/catalog.py`、`services/tools/runs.py`、`db/models/capabilities.py` | 已完成 | 本轮增加按 name 去重，避免内置工具重复显示；执行仍由代码 handler 完成。 | P0 |
| Agent 可配置工具、Skill、MCP 权限，并在页面模式正常加载 | `frontend/src/features/agents/components/AgentDirectoryDrawer/` | 已完成 | 本轮修复 `asPage` 模式不加载模型/工具/Skill/MCP 目录；旧授权工具会显示为 disabled legacy 选项，避免保存时丢配置。 | P0 |
| Skill 包化能力：manifest、runtime、测试、版本、依赖 | `backend/src/app/services/skills/` | 已实现，需持续加固 | `prompt/agent/mcp/script` runner 和 legacy adapter 已拆分；`mcp_skill` 走记录化 MCP 调用，`script_skill` 必须声明 `file.write` + `sandbox.run` 依赖并通过受控工具链执行，不应宣称生产级插件沙箱。 | P1 |
| MCP 服务管理、发现、健康检查、调用记录 | `backend/src/app/services/mcp/`、`backend/src/app/api/mcp.py` | 已实现，需持续加固 | HTTP/stdio/SSE-WS transport 分层已存在；外部网络、鉴权和超时策略依赖运行环境。 | P1 |
| 单聊 Agent 走完整 Function Calling Loop | `backend/src/app/services/agents/function_loop.py`、`tool_loop.py`、`direct.py` | 已完成 | 真实模型是否选择 tool_calls 取决于供应商；后端保留产物请求兜底和权限拒绝路径。 | P0 |
| 群聊 workflow 是事实来源，agent/tool/skill/mcp/artifact 节点真实执行 | `backend/src/app/services/workflows/engine.py`、`nodes/`、`scheduler.py`、`runtime.py` | 已完成 | 当前支持基础 DAG、并行、条件/循环基础语义；Artifact 节点已走统一 `artifact.create_*` 工具链并回写真实 `artifact_id/export_url`；节点失败策略支持 `stop/retry/skip`，`retry_count` 和 `node.retry` 事件已持久化；复杂人工审批和版本发布不在当前完成范围。 | P0 |
| 工作流画布可编辑、可拖拽、连线、节点运行态可见 | `frontend/src/features/workflow/`、`features/chat/components/drawers/WorkflowCanvas.tsx` | 已实现，需持续加固 | 已迁到工作台内嵌模式并保留完整画布；本轮修复返回聊天和按钮事件冒泡。 | P1 |
| SSE/WS 事件、停止响应、正在回答状态收敛 | `backend/src/app/services/chat/cancellation.py`、`finalizer.py`、`realtime/`、`frontend/src/api/message.ts`、`frontend/src/lib/runningConversations.ts` | 已实现，需持续加固 | 已有回归测试覆盖 message_stop / generation_finished 边界；跨进程运行需 Redis 或 sticky session。 | P0 |
| 文件系统像云盘/IDE 一样展示工作区文件 | `backend/src/app/api/workspace_files.py`、`services/files/workspace_*`、`frontend/src/features/workspaceFiles/` | 已实现，需持续加固 | 上传、产物、沙箱、项目文件聚合已实现；Office 预览依赖 LibreOffice，缺失时降级并提示。 | P1 |
| 产物生成真实 PDF/DOCX/PPTX/XLSX/HTML，支持预览和主格式下载 | `services/tools/builtins/artifact/`、`services/document_model/`、`api/artifacts.py`、`features/preview/` | 已实现，需持续加固 | PDF/DOCX 已使用 DocumentModel 渲染；Office 在线预览走转 PDF 缓存，环境未安装 LibreOffice 时降级。 | P0 |
| 沙箱真实受控执行，工作区隔离 | `services/tools/builtins/sandbox/`、`services/workspaces/filesystem.py`、`api/sandbox.py` | 已完成 | 本地执行有命令白名单、cwd 限制、超时和输出截断；生产容器隔离策略由部署环境承载。 | P0 |
| 上下文系统支持真实 role history、附件、工具结果、会话状态 | `services/context/`、`services/agents/function_messages.py` | 已完成 | 工作区长期记忆只在用户明确要求时写入，不自动跨会话保存闲聊。 | P0 |
| 多智能体 V2：ConversationSessionManager、TechLeadScheduler、Watchdog 最小闭环 | `backend/src/app/services/conversation_session_manager.py`、`backend/src/app/services/runtime/generation_records.py`、`backend/src/agent_runtime/`、`backend/src/app/persistence/sqlalchemy_backend.py` | 已实现，需持续加固 | 运行时骨架、调度器、看门狗、状态报告解析和测试存在；Generation / AgentRun 历史已写入 `Conversation.extra.runtime`，Blackboard / Agent Context 可通过 SQLAlchemyBackend 持久化恢复；消息、SSE 和 WebSocket 路径统一解析 `workflow/tech_lead` 调度策略，Session 复用会感知策略变化。 | P1 |
| 完整 Actor 化、Blackboard 协商式调度、分布式多 Agent 生命周期 | `docs/architecture/multi-agent-v2-design.md` | Roadmap | 属于长期架构计划，不应作为当前已交付功能承诺；当前只保留最小闭环和适配层。 | P2 |
| RBAC / 审计后台 | `api/security_ops.py`、`services/audit.py`、`db/models/security.py`、`frontend/src/features/platform/components/SecurityOpsPanel.tsx` | 已实现，需持续加固 | 权限和审计表/API 存在；用户角色更新已同步 `User.role` 与 `UserRole` 关系并写入审计；平台控制台已支持审计详情查看和用户角色变更。企业级权限审批流、复杂审计检索仍是后续增强。 | P2 |
| 部署 / 远程控制生产级能力 | `api/deployments.py`、`services/deployments.py`、`api/sandbox.py`、`services/tools/builtins/sandbox/` | 已实现，需持续加固 | 预览部署、回滚、日志、健康检查和审计已闭环；容器/云部署在本地环境会返回明确降级失败。生产级远程控制、容器隔离和云部署仍是 roadmap。 | P2 |

## 本轮收敛项

- `/api/v1/tools` 改为通过 `services/tools/catalog.py` 查询和同步工具目录。
- `services/tools/catalog.py` 按工具名去重，内置工具优先使用系统同步记录。
- `api/tools.py` 的工具调用改为通过 `services/tools/executor.py`，确保执行链写入调用记录。
- `seed.py` 同步内置工具走新版 catalog，且不再覆盖已有 Agent 的 `config.tools`。
- `AgentDirectoryDrawer` 在 drawer 和 page 两种模式下都加载模型、工具、Skill、MCP 目录。
- Agent 编辑时，如果已有授权工具不在当前目录中，会作为 disabled legacy 选项展示，防止用户保存时误丢旧配置。
- `tool_registry.py` 降级为兼容 shim，真实逻辑迁移到 `services/tools/*`。
- 工作流内嵌画布“返回聊天”切换状态和路由同步，悬浮按钮点击不再冒泡给 React Flow。
- SQLAlchemy 持久化后端改为替换 `Conversation.extra` JSON，确保 Blackboard 版本、结构化摘要、KV 状态和 Agent 私有上下文栈能跨 Session 恢复。
- Workflow Artifact 节点不再使用旧 demo HTML 路径，改为通过 `execute_tool_by_name()` 调用真实 `artifact.create_pdf/docx/xlsx/pptx/html/web_app`，并发布真实产物和预览消息事件。
- WebSocket V2 runtime 启动 generation 时会创建可恢复运行记录，消费 runtime 事件时更新 AgentRun 状态、调度决策和 watchdog 事件，完成/失败/取消后收敛到终态。
- WorkflowRun 的 `node_states` 新增 `retry_count`，工作流引擎支持节点级 `stop/retry/skip` 失败策略，并用测试覆盖失败结果重试、异常重试和跳过后继续下游。
- 消息入口、SSE 兼容入口和 WebSocket 入口统一使用 `services/chat/scheduling.py` 解析调度策略；有 workflow 的群聊默认走 `workflow`，显式切换 `tech_lead` 会重建对应 Session，避免复用旧调度器。
- 安全后台的用户角色更新会同步 `users.role` 与 `user_roles`，默认保留 `ROLE_USER` 并追加提升角色，同时写入 `security.user.role.update` 审计日志；前端安全运营面板已支持直接变更用户角色并展开审计详情。
- 预览部署迁入 `services/deployments.py`，创建和 `deploy.preview` 工具调用都执行产物可访问性健康检查；容器部署无运行时时会以 failed 状态和清晰错误降级，并写入部署审计。
- Skill manifest 现在支持 `mcp_skill` 和 `script_skill` runtime；脚本 Skill 只有在 manifest 显式依赖 `file.write` 与 `sandbox.run` 时才会写入脚本和输入文件，并通过同一沙箱工具执行，运行记录落到 `SkillRun` 与 `ToolInvocation`。
- Skill manifest 更新会保存可恢复版本快照和 hash；manifest tests 通过 `SkillRuntime` 生成 suite/case 级测试报告，依赖检查会从数据库 ToolDefinition / MCP / Skill 目录返回 resolved 明细。

## 2026-06-04 Skill 包审计加固

- `services/skills/versions.py` 现在会为 manifest 生成稳定 SHA-256 指纹；每次更新都会把前一版完整 manifest 快照、summary、变更字段、操作者、替换目标写入 `skills.metadata.versions`，并在当前 metadata 上保存 `manifest_hash`、`manifest_updated_at`、`manifest_updated_by`。
- `services/skills/testing.py` 的 manifest tests 通过 `SkillRuntime` 执行，报告会持久化到 `skills.metadata.test_reports`，包含 suite id、manifest hash、依赖解析报告、每个 case 的输入、断言、输出摘要、provider status 和 `SkillRun.run_id`。
- `services/skills/dependencies.py` 的 Tool 依赖解析改为以数据库 `tool_definitions` 为目录来源，同时返回 Tool / MCP / Skill 的 resolved 明细；缺失、禁用、不可见、无用户上下文等情况会给出可审计 reason。
- 覆盖测试：`tests/test_skill_packages.py` 新增 manifest 版本快照、case 级测试报告、数据库工具目录依赖解析用例。

## Roadmap 边界

以下内容保留在架构文档中，但当前不能写成“已完整实现”：

- 完整 Actor 化 Agent 生命周期。
- 分布式 Blackboard 与跨进程 Agent 私有上下文同步。
- 多 Agent 协商式调度和冲突仲裁。
- 生产级远程控制、容器沙箱和云端部署平台。
- 企业级权限审批流、复杂审计检索和组织级权限策略。

这些方向可以继续演进，但新增实现应保持当前模块边界：`chat -> workflows/agents -> tools/skills/mcp -> llm/files/artifacts/sandbox`，避免把新逻辑重新堆回旧 shim。

## 2026-06-04 MCP 调用链路加固

- `services/mcp/invocation.py` 在 allowlist 拒绝、参数 schema 校验失败、transport 超时、鉴权失败和不支持的 SSE/WebSocket transport 降级时，都会创建并完成 `McpToolInvocation`，调用结果包含稳定 `error_code` 和可读 `error_message`。
- `services/mcp/transports/common.py` 明确规则：`server.tools` 中显式禁用的工具优先于 `tool_filter` 通配符，避免 `echo.*` 重新放开 `echo.secret` 这类禁用工具。
- `services/mcp/transports/http.py` 对 HTTP timeout、request error、401/403 鉴权错误返回清晰诊断；SSE/WebSocket transport 目前走显式降级入口，不伪装成 HTTP 调用。
- `/mcp-servers/{id}/probe` 不再在 API 路由里硬编码默认工具；`services/mcp/discovery.py` 会对 HTTP / stdio 优先发起真实 JSON-RPC `tools/list`，刷新 `server.tools`，并把探测来源、错误和工具数量写入 `server.metadata.last_probe`。
- 本地演示 `agenthub-mcp-filesystem` stdio 命令保留受控内置适配目录，缺少外部二进制时以 degraded probe 记录降级原因，避免把普通第三方 MCP 误判为在线。
- 服务健康状态只在真实连接/transport 失败时标记 offline；allowlist 或参数错误不会误判 MCP Server 离线。
- 覆盖测试：`tests/test_capability_systems.py` 中新增 allowlist、schema failure、timeout、SSE/WebSocket 降级记录、HTTP tools/list 探测和 probe 失败诊断用例。
