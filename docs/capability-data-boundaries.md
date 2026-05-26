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

内置工具的真实执行仍在 `backend/app/services/tools/builtin_executor.py`。自定义 Python 工具走 `backend/app/services/tools/custom.py`。统一入口是 `backend/app/services/tools/executor.py`，执行前会读取 `ToolDefinition`、校验参数、检查权限并写入 `tool_invocations`。

旧入口 `backend/app/services/tools/registry.py` 保留为 shim，方便旧代码继续导入。

## MCP

`mcp_servers` 只保存外部服务器配置、工具发现结果、启停状态和归属关系。真实连接与调用逻辑在 `backend/app/services/mcp/`：

- `catalog.py`：server 可见性、权限、表初始化
- `discovery.py`：manifest 导入、工具发现、健康探测
- `transports.py`：HTTP / stdio transport
- `schema.py`：MCP tool 参数校验
- `invocation.py`：调用、错误回填、审计日志

调用记录写入 `mcp_tool_invocations`。旧入口 `backend/app/services/mcp_runtime.py` 保留为 shim。

## Skill

`skills` 是 Skill 包目录，兼容旧 prompt Skill，同时支持 `SKILL.md + manifest + scripts/references/assets` 的包化结构。Skill 不承载具体工具实现，只声明 prompt、依赖、权限和运行策略。

`backend/app/services/skills/` 的职责：

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
