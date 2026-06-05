# 能力体系数据边界

AgentHub 将 Tool、MCP、Skill 拆成两层职责：

- 数据库目录层：保存能力目录、分类、权限、schema、启停状态、版本、归属、运行记录和审计线索。
- 代码执行层：保存真实执行逻辑，包括内置 Tool handler、MCP transport、Skill runtime、权限校验和 JSON Schema 校验。

## Tool

`tool_definitions` 是统一工具目录。内置工具也会由 seed/ensure 同步到该表：

- `type=builtin`
- `owner_id=null`
- `is_builtin=true`
- `builtin_handler=<tool name>`
- `implementation.builtin_handler=<tool name>`

内置工具的真实执行仍在 `backend/src/app/services/tools/builtins/executor.py` 以及 `builtins/file/`、`builtins/artifact/`、`builtins/sandbox/` 等领域目录。自定义 Python 工具走 `backend/src/app/services/tools/custom.py`。统一入口是 `backend/src/app/services/tools/executor.py`，执行前会读取 `ToolDefinition`、校验参数、检查权限并写入 `tool_invocations`。

旧入口 `backend/src/app/services/tool_registry.py` 和 `backend/src/app/services/tools/registry.py` 仅保留为 shim，方便旧代码继续导入；历史 awaitable 适配集中在 `services/tools/legacy_registry.py`；新代码应直接使用 `services/tools/catalog.py`、`executor.py` 和 `permissions.py`。

## MCP

`mcp_servers` 只保存外部服务器配置、工具发现结果、启停状态和归属关系。真实连接与调用逻辑在 `backend/src/app/services/mcp/`：

- `catalog.py`：server 可见性、权限、表初始化
- `discovery.py`：manifest 导入、工具发现、健康探测
- `transports/`：HTTP / stdio / SSE-WS transport
- `schema.py`：MCP tool 参数校验
- `invocation.py`：调用、错误回填、审计日志

调用记录写入 `mcp_tool_invocations`。旧入口 `backend/src/app/services/mcp_runtime.py` 保留为 shim。

## Skill

`skills` 是 Skill 包目录，兼容旧 prompt Skill，同时支持 `SKILL.md + manifest + scripts/references/assets` 的包化结构。Skill 不承载具体工具实现，只声明 prompt、依赖、权限和运行策略。

`backend/src/app/services/skills/` 的职责：

- `manifest.py`：manifest 标准化和校验
- `package.py`：包解析、安装、删除
- `context.py`：Agent 激活 Skill 后注入模型上下文
- `runtime.py`：统一运行入口
- `dependencies.py`：Tool / MCP / Skill 依赖检查
- `testing.py`：测试运行和报告
- `versions.py`：manifest 版本记录

运行记录写入 `skill_runs`。旧 `skill.<id>` Function Call 仍可用，执行时走 `SkillRuntime`。

## 测试数据隔离

pytest 会设置 `AGENTHUB_TESTING=1`，并使用 `backend/var/test/agenthub_pytest_<pid>.db` 作为独立 SQLite 测试库。测试结束后会尝试删除该文件，避免 Acceptance MCP、`custom_echo_acceptance`、测试 Skill 等数据污染开发/演示数据库。

应用启动 seed 会执行 `cleanup_acceptance_residue()`，软删除历史误写入演示库的验收测试残留，包括 Acceptance MCP、`custom_echo_acceptance`、重复 `Release Notes Skill` 和 `Filesystem Read Skill`。
# 2026-06-05 External Coding Agent 数据边界

Codex / Claude Code 在 AgentHub 中不是一次性 sandbox 命令，而是外部长任务 Coding Agent。平台通过 `services/external_agents/` 的 Adapter 层接入，再映射为 Tool / MCP / Skill 可调用能力。

数据职责划分：

- 数据库 `external_agent_runs`：保存运行目录、provider、状态、命令 argv（已脱敏）、stdout/stderr tail、变更文件、退出码、耗时和错误。
- `tool_definitions`：登记 `external_agent.probe`、`external_agent.run_codex`、`external_agent.run_claude_code`、`external_agent.cancel`、`external_agent.status`，用于目录、授权和 Function Calling 暴露。
- `tool_invocations`：每次通过 Tool 执行外部 Agent 时写入统一工具调用记录。
- 代码执行层：`process_manager.py` 负责 `shell=False`、数组 argv、超时、取消和输出流；`workspace.py` 负责 workspace/conversation/agent 目录隔离。
- 前端：只展示 installed/degraded、命令来源、最近运行记录和脱敏输出摘要，不展示 API Key、token 或 CLI 登录态。

安全边界：

- CLI 路径来自 `CODEX_CLI_PATH` / `CLAUDE_CODE_CLI_PATH` 或 PATH 探测；缺失时返回 degraded。
- 运行目录必须在当前 workspace root 内；禁止绝对路径逃逸和 `..`。
- stdout/stderr、命令参数和错误信息都经过 secret redaction。
- Skill/MCP 如需调用外部 Agent，仍必须走 `external_agent.*` Tool 权限和运行记录，不能绕过 executor。
## 2026-06-05 Artifact / Tool / File 数据边界补充

- `ToolDefinition` 与 `ToolInvocation` 只记录工具目录、权限、schema、参数与执行结果；真实 artifact 文件由 artifact builtin executor 写入工作区 artifacts 存储，并由 `Artifact` / `ArtifactVersion` 记录版本。
- `preview_card` 是聊天消息，不是前端临时状态。每张卡必须能通过 `artifact_id` 找到真实 Artifact，并通过 `export_url` 下载主格式文件。
- 工作区文件系统只聚合当前 workspace 下的 uploads / artifacts / sandbox / exports / projects。预览接口不得跨 workspace 解析路径，失败时返回可读错误，不返回空白成功响应。
- 沙箱 cwd 由 workspace filesystem resolver 生成，工具和外部 Coding Agent 都不得传入逃逸路径或 shell 拼接命令。

## 2026-06-05 Runtime Tool Result 边界

`agent_runtime` 只产生工具调用意图和运行事件，不直接伪造业务数据。所有工具副作用都必须通过 app 层能力目录执行：

```text
AgentActor / Workflow node
  -> ToolExecutorAdapter
  -> async_tool_loop.execute_tool_by_name()
  -> tools.catalog / tools.executor / permissions / schema validation
  -> ToolInvocation
  -> optional Artifact / FileAsset / SandboxSession / SkillRun / McpToolInvocation
```

Artifact 工具成功后的数据边界：

- `Artifact` 保存真实产物元数据、主格式文件和 preview/export 信息。
- `Message(content_type="preview_card")` 保存聊天卡片，`rawContent.artifact_id` 是预览唯一入口。
- `ToolInvocation.output.artifact_id` 是 runtime 将工具结果映射回聊天的依据。
- 前端只能展示后端推送或 DB 恢复的 preview_card，不能根据用户关键词自行创建卡片。

旧兼容边界：

- 旧 `function_loop.py`、`direct.py` 可以继续被 legacy tests 或旧 API 调用，但必须通过同一 `execute_tool_by_name()` 和 artifact/message 映射结果。
- 新工具、Skill、MCP、External Agent 运行记录不得绕过 `ToolDefinition` 授权和运行记录。
