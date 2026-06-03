# AgentHub Docs

这个目录放项目的补充说明，主要服务三类人：

- 演示者：快速知道系统有哪些功能、怎么走完整链路。
- 开发者：快速找到每个功能对应的前端、后端、数据模型和测试文件。
- 维护者：知道模型、Agent、工具、Skill、MCP、文件、产物和工作流之间怎么连接。

## 文档索引

- [功能使用说明](./functional-guide.md)：按产品功能解释怎么使用、每个功能的闭环是什么。
- [文件职责地图](./file-map.md)：说明主要目录和关键文件分别负责什么。
- [开发维护手册](./development-guide.md)：本地环境、迁移、启动、测试和常见改动入口。
- [Agent 与工作流运行机制](./agent-workflow-runtime.md)：说明单聊、群聊、画布优先编排、Agentic Loop、工具调用和运行态持久化。

## 阅读建议

如果只是演示，先看 `functional-guide.md`，再看 `agent-workflow-runtime.md` 的“演示链路”。

如果要继续开发，先看 `file-map.md`，再按要改的功能跳到对应 API、service、frontend 组件和测试。

如果要排查问题，优先看：

- 消息不流式：`frontend/src/api.ts`、`backend/app/api/messages.py`、`backend/app/services/events.py`、`backend/app/services/runtime_service.py`、`backend/agent_runtime/`
- Agent 不按权限调用工具：`backend/app/services/agentic_runtime.py`、`backend/app/services/tool_registry.py`、`backend/db/models/`
- 工作流画布保存或运行异常：`backend/app/api/conversations.py`、`backend/app/services/runtime_service.py`、`backend/agent_runtime/`、`frontend/src/App.tsx`
- 文件/产物异常：`backend/app/api/files.py`、`backend/app/services/file_tools.py`、`backend/app/api/artifacts.py`、`backend/app/services/artifact_exports.py`
- 模型调用失败：`backend/app/core/config.py`、`backend/app/services/ark.py`、`backend/app/services/llm_gateway.py`

