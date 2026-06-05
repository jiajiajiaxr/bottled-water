# AgentHub Docs

> 当前后端主架构位于 `backend/src/`；`backend/app-old/` 仅作为历史实现和迁移参考保留，不再作为新功能开发目录。

这个目录放项目的补充说明，主要服务三类人：

- 演示者：快速知道系统有哪些功能、怎么走完整链路。
- 开发者：快速找到每个功能对应的前端、后端、数据模型和测试文件。
- 维护者：知道模型、Agent、工具、Skill、MCP、文件、产物和工作流之间怎么连接。

## 文档索引

- [功能使用说明](./functional-guide.md)：按产品功能解释怎么使用、每个功能的闭环是什么。
- [文件职责地图](./file-map.md)：说明主要目录和关键文件分别负责什么。
- [开发维护手册](./development-guide.md)：本地环境、迁移、启动、测试和常见改动入口。
- [Agent 与工作流运行机制](./agent-workflow-runtime.md)：说明单聊、群聊、画布优先编排、Agentic Loop、工具调用和运行态持久化。
- [实现状态与文档承诺审计](./implementation-status.md)：对照文档承诺、代码位置、完成状态和 roadmap 边界。

## 阅读建议

如果只是演示，先看 `functional-guide.md`，再看 `agent-workflow-runtime.md` 的“演示链路”。

如果要继续开发，先看 `file-map.md`，再按要改的功能跳到对应 API、service、frontend 组件和测试。

如果要排查问题，优先看：

- 消息不流式：`frontend/src/api/`、`backend/src/app/api/messages.py`、`backend/src/app/services/realtime/event_bus.py`、`backend/src/app/services/runtime_service.py`、`backend/src/agent_runtime/`
- Agent 不按权限调用工具：`backend/src/app/services/agents/function_loop.py`、`backend/src/app/services/agents/tool_loop.py`、`backend/src/app/services/tools/`、`backend/src/db/models/`
- 工作流画布保存或运行异常：`backend/src/app/api/conversations.py`、`backend/src/app/services/workflows/`、`frontend/src/features/workflow/`
- 文件/产物异常：`backend/src/app/api/files.py`、`backend/src/app/api/artifacts.py`、`backend/src/app/services/files/`、`backend/src/app/services/tools/builtins/artifact/`
- 模型调用失败：`backend/src/app/core/config.py`、`backend/src/app/services/llm/ark.py`、`backend/src/app/services/llm/gateway.py`

