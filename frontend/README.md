# AgentHub 前端项目概览

> 本文档面向 AI 助手，旨在帮助快速理解项目结构、关键决策和修改边界，**无需翻阅代码即可定位模块**。

---

## 一、项目定位

AgentHub（代号 `fish`）前端是一个**多智能体协作 IM 工作台**的 Web 界面，核心能力包括：

- **即时通讯**：单聊 / 群聊（多 Agent 会话）、消息引用、文件附件、流式回复
- **Agent 管理**：Agent 目录、能力配置、测试
- **工作流编排**：可视化画布（@xyflow/react），支持 AI 生成工作流，节点类型包括 agent/tool/skill/mcp/condition/loop/review/artifact/end
- **产物生命周期**：Artifact 生成 → 预览 → Diff → 部署
- **平台管理**：工作区、项目、文件资产、知识库、模型配置、MCP 服务器、工具/Skill、沙箱、远程连接、审计日志
- **文档站**：独立 `/docs` 路由的纯前端文档页面

---

## 二、技术栈

| 层 | 选型 | 说明 |
|---|---|---|
| 框架 | React 18 + TypeScript | StrictMode 开启 |
| 构建 | Vite 6 | `vite.config.ts` 中配置代理 `/api/v1` 和 `/ws` |
| UI 组件 | Ant Design 5 | 中文 locale，`colorPrimary: #1677ff`，`borderRadius: 8` |
| 路由 | React Router 6 | BrowserRouter，路由定义在 `src/router/AppRouter.tsx` |
| 状态管理 | Zustand 5 | 按域拆分多个 store，无持久化中间件（除 `thinkingEnabled` 手动写 localStorage） |
| 流式通信 | SSE + WebSocket | SSE 通过 `fetch + ReadableStream` 解析；WebSocket 封装在 `api/websocket.ts` |
| HTTP 客户端 | 自定义 fetch 封装 | `api/client.ts` 提供 `request/get/post/patch/del`，统一错误处理 `ApiError` |
| 样式 | SCSS 模块 | `src/styles/` 下 12 个 partial，入口 `index.scss` |
| 测试 | Vitest + jsdom + @testing-library/react | 配置在 `vitest.config.ts`，setup 在 `tests/setup.ts` |
| 包管理 | pnpm | 所有命令前缀 `pnpm` |

---

## 三、目录结构

```
frontend/
├── src/
│   ├── api/              # HTTP 客户端 + 各域 API 封装 + SSE/WebSocket 协议
│   │   ├── client.ts     # 核心：request, get, post, patch, del, sse, unwrap, 拦截器
│   │   ├── message.ts    # 消息：SSE 流解析 + WebSocket 发送 + dispatchStreamEvent
│   │   ├── websocket.ts  # WebSocket 连接管理（按 conversationId 缓存）
│   │   ├── SSE_PROTOCOL.md  # 前端反推的 SSE 协议文档（重要参考）
│   │   └── [auth|agent|conversation|...].ts  # 各域 REST API
│   ├── components/       # 全局共享组件（目前几乎为空，TODO）
│   │   ├── common/       # 通用组件（Button, Modal 等封装）
│   │   └── layout/       # 布局组件（Header, Sidebar 等）
│   ├── features/         # 按功能域组织的模块（主要代码在这里）
│   │   ├── agents/       # Agent 目录抽屉
│   │   ├── auth/         # 登录屏
│   │   ├── chat/         # 聊天面板、消息气泡、会话侧边栏、各种抽屉
│   │   ├── platform/     # 平台控制抽屉（工作区/项目管理）
│   │   ├── preview/      # 产物预览面板（Artifact 预览、部署状态）
│   │   ├── settings/     # 全局设置抽屉、模型设置
│   │   ├── workspace/    # 工作区抽屉
│   │   ├── workspaceFiles/  # 工作区文件浏览器
│   │   └── workflow/     # 工作流画布（最复杂的模块，约 20+ 文件）
│   ├── hooks/            # 全局业务 Hooks（6 个）
│   │   ├── useStreamingMessages.ts   # 流式消息状态管理（核心）
│   │   ├── useMessageOperations.ts   # 消息发送编排（SSE/WS 调用）
│   │   ├── useWorkbenchActions.ts    # Workbench 业务动作封装
│   │   └── ...
│   ├── lib/              # 纯工具函数 / 渲染组件
│   │   ├── message.ts    # makeMessage, attachment 提取, 工具输出剥离
│   │   ├── markdown.tsx  # MarkdownContent 组件
│   │   ├── workflow.ts   # 工作流节点类型/创建
│   │   └── ...
│   ├── pages/            # 页面级组件（路由入口）
│   │   ├── WorkbenchPage/    # 主工作台（核心页面，433 行）
│   │   ├── WorkflowStudioPage/  # 独立工作流编排页面
│   │   ├── DocsPage/         # 文档站（纯前端，316 行）
│   │   └── LoginPage/
│   ├── router/           # 路由配置
│   │   ├── AppRouter.tsx     # 根路由（认证守卫 + 路由表）
│   │   ├── WorkbenchRoute.tsx
│   │   └── LoginRoute.tsx
│   ├── store/            # Zustand Store（8 个）
│   │   ├── useConversationStore.ts   # 会话列表 + activeId + thinkingEnabled 持久化
│   │   ├── useMessageStore.ts        # 历史消息数组 + messageVersions Map
│   │   ├── useAgentStore.ts
│   │   ├── useWorkspaceStore.ts
│   │   ├── useArtifactStore.ts
│   │   ├── useTaskStore.ts           # 后台任务轮询状态
│   │   └── useUIStore.ts             # 所有抽屉/模态框开关状态
│   ├── styles/           # SCSS 模块
│   │   ├── index.scss    # 入口：@use 所有 partial
│   │   ├── _variables.scss
│   │   ├── _chat.scss
│   │   ├── _workflow.scss
│   │   └── ...
│   ├── types/            # TypeScript 类型定义（15+ 文件）
│   │   ├── chat.ts       # Conversation, ChatMessage, Participant, MessageAttachment
│   │   ├── messages.ts   # StreamAssistantHandlers, MessageBody
│   │   ├── workflow.ts   # WorkflowNode, ConversationWorkflow, WorkflowRun
│   │   └── ...
│   └── utils/
│       └── logger.ts     # 前端日志：内存队列 → 批量 POST /api/v1/logs → sendBeacon
├── tests/                # 测试文件（11 个）
│   ├── setup.ts          # jsdom mock (matchMedia, getComputedStyle)
│   └── *.test.{ts,tsx}   # 组件/逻辑测试
├── docs/                 # 项目文档（位于仓库根目录，非前端专属）
└── [配置文件]
    ├── vite.config.ts
    ├── vitest.config.ts
    ├── tsconfig.json       # src 目录，moduleResolution: Bundler
    ├── tsconfig.node.json  # vite.config.ts，types: ["node"]
    └── eslint.config.js
```

---

## 四、关键架构决策

### 4.1 消息状态分离模型

这是**最核心**的架构设计：

| 状态 | 位置 | 数据类型 | 生命周期 |
|---|---|---|---|
| **历史消息** | `useMessageStore.historyMessages` | `ChatMessage[]` | 会话切换时重新加载 |
| **流式消息** | `useStreamingMessages.streamingMessages` | `Map<agentId, ChatMessage>` | 仅活跃流传输期间存在 |
| **消息版本号** | `useMessageStore.messageVersions` | `Map<messageId, number>` | 用于 `MessageBubble.memo` 优化 |

**为什么分离？**
- 流式消息需要高频更新（每 token 一次），历史消息数组 immutable 更新成本太高
- Map 的 O(1) 更新避免了数组遍历
- 流式结束后通过 `onMessageEnd` 归档到历史消息数组，同时从 Map 删除

**为什么需要 version？**
- `MessageBubble` 使用 `React.memo`，以 `version` 作为比较键
- 流式 token 更新时只递增对应 messageId 的 version，触发单条消息重渲染

### 4.2 流式通信双协议

项目同时支持 SSE 和 WebSocket，但**当前生产环境使用 WebSocket**（`sendMessageWs`）：

- **SSE**（`sendMessage`）：基于 `fetch + ReadableStream`，自定义 `parseSSEStream` 生成器解析 event/data 格式。保留用于降级或调试。
- **WebSocket**（`sendMessageWs`）：`api/websocket.ts` 按 `conversationId` 缓存连接，支持复用。消息格式为 JSON-RPC-like：`{ event, data, requestId }`。

两者共用同一套 `StreamAssistantHandlers` 和 `dispatchStreamEvent` 逻辑。

### 4.3 Store 职责划分

| Store | 职责 | 是否持久化 |
|---|---|---|
| `useConversationStore` | 会话列表、activeId、分类标签、运行中标记、thinkingEnabled（localStorage） | 部分 |
| `useMessageStore` | 历史消息、messageVersions | 否 |
| `useUIStore` | 所有抽屉/模态框的开关状态、scheduleMode | 否 |
| `useAgentStore` | Agent 列表 | 否 |
| `useWorkspaceStore` | 工作区列表、activeWorkspaceId | 否 |
| `useArtifactStore` | 当前产物、文件列表、知识库、部署状态 | 否 |
| `useTaskStore` | 后台任务列表 | 否 |

### 4.4 工作流画布

使用 `@xyflow/react`（React Flow）实现：

- `WorkflowStudioContent`：主容器，支持 `embedded` 模式（嵌入在聊天面板内）和独立页面模式
- `WorkflowCanvasPanel`：画布核心（节点、边、选中状态、运行时覆盖层）
- `useWorkflowStudio`：封装画布所有状态逻辑（加载、保存、AI 生成、运行、节点选择/编辑）
- 节点类型：start → agent/tool/skill/mcp/condition/loop/review/artifact → end
- 工作流与对话绑定：每个对话可关联一个 `ConversationWorkflow`，运行时产生 `WorkflowRun`

---

## 五、重要修改边界

### 5.1 修改前必读

1. **文件大小红线**：项目规范要求单文件 ≤500 行。以下文件已接近或触及红线，修改时优先拆分：
   - `src/pages/WorkbenchPage/Workbench.tsx`（433 行）
   - `src/features/chat/components/ChatPanel/index.tsx`（270 行）
   - `src/features/chat/components/MessageBubble/index.tsx`（340 行）
   - `src/pages/DocsPage/index.tsx`（316 行）
   - `src/features/workflow/WorkflowStudioContent.tsx`（290 行）

2. **类型定义在 `src/types/`**：新增/修改实体类型时，需要同步更新对应文件，不要在组件内定义 interface。

3. **API 调用统一走 `src/api/index.ts`**：不要直接 fetch，使用 `api.xxx()` 或 `request/get/post/patch/del`。

4. **样式优先用 SCSS partial**：新增模块样式在 `src/styles/_xxx.scss` 中定义，然后在 `index.scss` 中 `@use`。

5. **中文注释规范**：所有 JSDoc/注释使用中文。

### 5.2 常见修改场景

| 场景 | 入口文件 | 关联文件 |
|---|---|---|
| 新增消息类型/字段 | `src/types/chat.ts` | `src/lib/message.ts`, `src/features/chat/components/MessageBubble/index.tsx` |
| 修改流式行为 | `src/hooks/useStreamingMessages.ts` | `src/hooks/useMessageOperations.ts`, `src/api/message.ts` |
| 新增工作流节点类型 | `src/types/workflow.ts` | `src/features/workflow/canvas/workflowCanvasElements.tsx`, `src/lib/workflow.ts` |
| 新增 API 端点 | `src/api/[domain].ts` | `src/api/index.ts` |
| 新增抽屉/面板 | `src/features/[domain]/components/` | `src/store/useUIStore.ts`, `src/pages/WorkbenchPage/WorkbenchDrawers.tsx` |
| 修改全局样式变量 | `src/styles/_variables.scss` | 所有引用该变量的 partial |

---

## 六、环境变量

通过 `vite` 的 `loadEnv` 加载，前缀 `VITE_`：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `VITE_FRONTEND_PORT` | `5173` | 开发服务器端口 |
| `VITE_API_BASE_URL` | `http://localhost:8888` | 后端 API 代理目标 |
| `VITE_WS_URL` | `ws://localhost:8888` | WebSocket 代理目标 |

---

## 七、命令速查

```bash
# 开发
pnpm dev

# 构建（tsc 类型检查 ×2 + vite build）
pnpm build

# 预览生产构建
pnpm preview

# Lint
pnpm lint
pnpm lint:fix

# 测试
pnpm vitest        # 交互模式
pnpm vitest run    # CI 模式
```

---

## 八、已知技术债务（详见 `EVALUATION.md`）

- `components/` 目录几乎为空，TODO 待填充
- `Upload` 组件未配置 `beforeUpload`/`action`，当前只是占位
- `Workbench.tsx` 体积过大，路由/工作区/会话/Agent 初始化逻辑混杂
- 多处 `eslint-disable-next-line react-hooks/exhaustive-deps`
- 类型定义中充斥 `"不清楚作用"` 的注释，说明数据流历史遗留问题
