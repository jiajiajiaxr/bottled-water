# Tool / MCP / Skill 模块迁移说明

本说明记录能力域重构后的模块边界，以及旧入口的保留原因和删除条件。

## 新模块边界

- Tool 内置能力：
  - `backend/app/services/tools/builtins/registry.py`：内置 Tool 元数据和官方 toolbox。
  - `backend/app/services/tools/builtins/executor.py`：内置 Tool 分发入口。
  - `backend/app/services/tools/builtins/artifact/`：产物生成、真实文件持久化、预览渲染、导出。
  - `backend/app/services/tools/builtins/file/`：文件提取、预览、转换和文件类 Tool 执行。
  - `backend/app/services/tools/builtins/sandbox/`：沙箱策略、命令运行器、sandbox/test 执行入口。
- MCP：
  - `backend/app/services/mcp/transports/common.py`：工具名、allowlist、环境变量清洗。
  - `backend/app/services/mcp/transports/http.py`：HTTP JSON-RPC 调用。
  - `backend/app/services/mcp/transports/stdio.py`：stdio 子进程调用。
  - `backend/app/services/mcp/transports/sse_ws.py`：SSE/WebSocket transport 预留入口。
- Skill：
  - `backend/app/services/skills/runners/prompt.py`：prompt skill 运行。
  - `backend/app/services/skills/runners/agent.py`：agent skill 运行。
  - `backend/app/services/skills/runners/mcp.py`：旧 MCP Skill 兼容运行。
  - `backend/app/services/skills/runners/script.py`：脚本 Skill 预留入口。

## 旧入口用途

这些旧入口只保留兼容导入，不承载业务逻辑：

| 旧入口 | 新目标 |
| --- | --- |
| `app.services.artifact_exports` | `app.services.tools.builtins.artifact.export` |
| `app.services.artifact_storage` | `app.services.tools.builtins.artifact.storage` |
| `app.services.artifact_content_model` | `app.services.tools.builtins.artifact.renderers` |
| `app.services.file_tools` | `app.services.tools.builtins.file` |
| `app.services.tools.artifact_executor` | `app.services.tools.builtins.artifact.executor` |
| `app.services.tools.builtin_executor` | `app.services.tools.builtins.executor` |
| `app.services.tools.sandbox_runner` | `app.services.tools.builtins.sandbox.executor` |
| `app.services.tools.registry` | `app.services.tools.catalog/executor/permissions` |
| `app.services.mcp_runtime` | `app.services.mcp.*` |
| `app.services.skills.execution` | `app.services.skills.runners.*` |

## 删除条件

旧入口可以删除的条件：

- `backend/app/` 和 `backend/tests/` 中不再直接 import 旧入口。
- 前端、脚本、外部插件没有引用旧 Python import 路径。
- 至少一个版本周期内无兼容导入告警或第三方扩展反馈。
- 删除前再次跑通 `uv run ruff check .` 和 `uv run pytest -q`。
