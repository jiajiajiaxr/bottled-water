# 开发维护手册

本文说明如何在本地开发、验证和修改 AgentHub。

## 1. 环境变量

后端配置集中在 `backend/app/core/config.py`。当前只读取：

- 项目根目录 `.env`
- `backend/.env`

推荐把主要配置放在项目根目录 `.env`。

常用变量：

```env
DATABASE_URL=sqlite:///./agenthub_dev.db
LLM_PROVIDER=ark
ARK_BASE_URL=...
ARK_ENDPOINT_ID=...
ARK_MODEL=...
ARK_API_KEY=...
```

说明：

- `LLM_PROVIDER=ark`：使用真实火山方舟适配器。
- `LLM_PROVIDER=mock`：使用本地 mock。
- `LLM_PROVIDER=auto`：有 key 时走真实模型，否则 mock。
- API Key 不应该写入前端代码，也不应该通过浏览器传递。

## 2. 安装依赖

后端使用 `uv` 管理 Python 3.11 运行时、虚拟环境和依赖锁定：

```powershell
uv sync --project backend --extra dev
```

前端：

```powershell
cd frontend
corepack pnpm install
```

## 3. 数据库迁移

```powershell
uv run --project backend --directory backend alembic upgrade head
```

迁移脚本位于：

- `backend/alembic/versions`

新增表或字段时：

1. 修改 `backend/db/models/` 下对应领域模型文件。
2. 新增 Alembic migration。
3. 更新 `backend/app/services/serialization.py` 里的输出结构。
4. 更新 `frontend/src/types.ts`。
5. 补 API 和测试。

## 4. 启动开发服务

后端：

```powershell
uv run --project backend --directory backend uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

前端：

```powershell
cd frontend
corepack pnpm dev
```

开发时前端通过 Vite 代理访问后端 `/api/v1`。

## 5. 测试命令

后端：

```powershell
uv run --project backend pytest -q
```

前端：

```powershell
cd frontend
corepack pnpm vitest run
corepack pnpm exec tsc --noEmit --pretty false
corepack pnpm build
```

E2E：

```powershell
cd frontend
corepack pnpm exec playwright test -c ..\e2e\playwright.config.ts
```

## 6. 常见开发入口

### 新增一个 API

1. 在 `backend/app/api` 下选择已有领域文件或新建文件。
2. 在 `backend/app/main.py` 注册 router。
3. 如果涉及数据库，修改 `backend/db/models/` 下对应领域模型文件和迁移。
4. 在 `backend/app/services/serialization.py` 增加输出转换。
5. 在 `frontend/src/api.ts` 增加 SDK 方法。
6. 在 `frontend/src/types.ts` 增加类型。
7. 在对应测试文件里补测试。

### 新增一个 Agent 字段

1. 修改 `backend/db/models/agents.py` 中 `Agent` 模型。
2. 增加 migration。
3. 修改 `agent_to_dict`。
4. 修改 `frontend/src/types.ts` 的 `Agent` / `AgentConfig`。
5. 修改 Agent 创建、编辑表单。
6. 修改 `backend/app/api/agents.py` 的创建和更新逻辑。
7. 如果影响执行，修改 `agentic_runtime.py` 或 `runtime_service.py` / `agent_runtime/`。

### 新增一个工作流节点类型

1. 修改 `frontend/src/types.ts` 的 `WorkflowNode` 约定。
2. 修改 `frontend/src/App.tsx` 的节点类型选项、创建默认配置、编辑表单。
3. 修改 `backend/app/api/conversations.py` 的 normalize 逻辑，确保 `type/config` 不丢失。
4. 修改 `backend/agent_runtime/workflow/` 或 `backend/app/services/runtime_service.py` 的执行逻辑。
5. 修改 `conversation.extra.workflow_runtime` 输出。
6. 增加 `tests/test_conversation.py` 和相关工作流测试。

### 新增一个内置工具

1. 在 `backend/app/services/tool_registry.py` 增加工具定义。
2. 在 `invoke_builtin_tool` 中实现真实执行。
3. 给官方 Agent 工具箱加权限。
4. 如果需要文件能力，优先复用 `file_tools.py`。
5. 前端工具目录会通过 `/tools` 自动展示。
6. 补 `tests/test_tools_files.py`。

### 新增一个文件格式

1. 在 `backend/app/services/file_tools.py` 增加提取、预览或生成逻辑。
2. 在 `backend/app/api/files.py` 接入到对应接口。
3. 如果需要作为产物导出，修改 `artifact_exports.py`。
4. 前端预览逻辑在 `PreviewPanel` 和附件预览处补展示。
5. 补文件工具测试。

### 调整模型供应商

1. 修改 `backend/app/services/ark.py` 或新增 provider service。
2. 修改 `backend/app/services/llm_gateway.py`。
3. 修改 `backend/app/api/models.py` 的配置和测试接口。
4. 修改全局设置表单。
5. 不要把 API Key 暴露到 `frontend/src`。

### 调整输出显示

内部规划、任务拆解、执行过程、审查草稿等内容不应该直接出现在最终聊天气泡里。

相关入口：

- 后端过滤：`backend/app/services/output_filter.py`
- 前端过滤：`frontend/src/App.tsx` 中的 `stripInternalAgentOutput`
- 编排生成：`backend/app/services/runtime_service.py`、`backend/agent_runtime/`

## 7. 数据流速查

发送消息：

```text
frontend Workbench.send
  -> api.sendMessage
  -> backend/app/api/messages.py
  -> Message 入库
  -> runtime_service.run / conversation_session_manager
  -> events 发布流式事件
  -> frontend api.streamConversation
  -> 聊天气泡增量更新
```

上传附件：

```text
frontend uploadFile
  -> /files/upload
  -> save_upload
  -> file_tools.extract_text_from_path
  -> FileAsset 入库
  -> 发送消息时 attachments 进入消息上下文
```

产物生成：

```text
Agent / tool
  -> tool_registry.invoke_builtin_tool
  -> artifacts.create_artifact
  -> Message preview_card
  -> 用户点击卡片
  -> PreviewPanel 加载 artifact
```

群聊工作流：

```text
send message
  -> load conversation.extra.workflow
  -> optional replan
  -> workflow_execution_order
  -> node type dispatch
  -> WorkflowRun.node_states
  -> final assistant message
```

## 8. 排障建议

- 页面空白：先跑 `corepack pnpm exec tsc --noEmit --pretty false`。
- 登录失败：查 `backend/app/api/auth.py` 和 `.env` 的 `SECRET_KEY`。
- 模型无响应：查 `LLM_PROVIDER`、`ARK_API_KEY`、`ARK_ENDPOINT_ID`，再看 `backend/app/services/ark.py`。
- 消息一直显示正在回答：查 `localRunningConversationIds` 清理逻辑和 `runtime_service.run` / `conversation_session_manager` 是否抛错。
- 工作流节点配置丢失：查 `conversations.py` normalize 是否保留 `type/config`。
- 产物打不开：查 `Artifact.content`、`artifact_exports.py` 和 `PreviewPanel`。
- MCP 调用失败：先 probe，再看 `McpToolInvocation` 记录。
