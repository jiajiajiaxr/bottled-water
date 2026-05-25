# AgentHub Backend Services

本目录按业务领域组织服务层代码。旧入口仍然保留为 shim，外部 API 不需要感知本次拆分。

## 依赖方向

- `chat/` 负责聊天入口编排，允许依赖 `workflows/`、`agents/`、`tasks/`、`realtime/`。
- `workflows/` 负责画布定义、DAG 顺序、WorkflowRun 运行态和规划补全，不依赖 API 层。
- `agents/` 负责单 Agent 执行、上下文构建和 Function Call 工具循环，可依赖 `tools/`、`llm_gateway`、`ark`、`realtime/`。
- `tools/` 负责工具目录、权限辅助、执行分发和内置工具实现入口，不依赖聊天编排。
- `realtime/` 只提供 EventBus/SSE/WebSocket 边界，不反向依赖业务模块。
- `tasks/` 负责 Task/Subtask 创建、状态数据结构和任务计划序列化。

## 模块职责

- `chat/orchestrator.py`：聊天编排主入口。保持原有 `run_orchestration(message_id)` 行为。
- `chat/artifacts.py`：聊天流中由工具产生的产物卡片事件发布。
- `workflows/definition.py`：工作流画布规范化、节点类型、DAG 执行顺序和默认并行画布。
- `workflows/planning.py`：任务规划和画布重规划提示，后续可扩展为 Master Agent 的画布补全能力。
- `workflows/runtime.py`：WorkflowRun 节点状态机和会话 extra 同步。
- `agents/tool_loop.py`：Agent 工具 schema 构造、Skill/MCP/内置工具执行分发，以及旧短循环兼容入口。
- `agents/function_loop.py`：单聊和群聊共用的 Agent 执行器，负责创建 assistant message、流式输出、工具调用事件、WorkflowRun 节点状态回写，以及 tool result -> role=tool -> final answer 的多轮闭环。
- `agents/direct.py`：单聊 Agent 执行，负责 Task/Subtask 生命周期，具体推理由 `agents/function_loop.py` 完成。
- `agents/replies.py`：画布/群聊中单个 Agent 的流式回复辅助。
- `tools/registry.py`：内置工具与自定义工具目录、调用分发。
- `tools/executor.py`：工具执行兼容入口，后续承载硬权限校验和参数校验。
- `tools/permissions.py`：工具权限名称规范化辅助。
- `realtime/event_bus.py`：内存 EventBus 和历史事件回放。
- `realtime/sse.py`、`realtime/websocket.py`：实时连接协议边界。
- `tasks/service.py`：从 prompt/plan 创建 Task/Subtask，输出 plan JSON。

## 兼容入口

以下旧模块仅做 re-export，便于既有 API、测试和第三方调用平滑迁移：

- `services/orchestrator.py`
- `services/agentic_runtime.py`
- `services/tool_registry.py`
- `services/events.py`

## 后续扩展方式

多 Agent Function Call 工作流应以 `workflows/definition.py` 的节点定义为入口，将每个 `agent` 节点编译成独立 `agents/tool_loop.py` 执行单元。并发执行时，每个节点应使用独立数据库 Session，只传递 ID，不跨任务共享 ORM 对象；WorkflowRun 状态更新统一收敛到 `workflows/runtime.py`。
