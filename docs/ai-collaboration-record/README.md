# AgentHub AI 协作开发记录包



本目录记录 AgentHub 从需求理解、架构设计、编码实现、缺陷修复、真实体验验收到发布包装的 AI 协作过程。它重点证明：项目不是简单“用了 AI 生成代码”，而是在项目负责人主导下，持续使用 Codex、Computer Use、Browser、本地运行环境、Git 历史和自动化验证形成了一套可复用的工程协作方法。



## 文件说明

| 文件 | 作用 |
| --- | --- |
| [00-feishu-doc-outline.md](./00-feishu-doc-outline.md) | 可复制到飞书文档的对外说明模板 |
| [01-collaboration-log.md](./01-collaboration-log.md) | 基于真实 Git 历史整理的 AI 协作开发过程记录 |
| [02-ai-collaboration-spec.md](./02-ai-collaboration-spec.md) | AI 协作 Spec：任务输入、验收口径、工程边界和证据要求 |
| [03-agent-rules.md](./03-agent-rules.md) | AI 协作 Rules：代码、权限、安全、提交和产物规则 |
| [04-skills-and-prompts.md](./04-skills-and-prompts.md) | AI 编程协作 Skills / Prompts：Codex、Computer Use、Browser、Git 和复盘模板 |
| [05-artifact-index.md](./05-artifact-index.md) | 产物地址索引：仓库、文档、运行入口、演示链路 |
| [skills/](./skills/) | 可复用 Skill 文件夹：按 Codex Skill 形态沉淀产品简报、仓库理解、架构审查、前端体验、自审、真实产物、能力审计、多 Agent 调试、部署验收、Git 证据和评审包装能力 |

## 证明重点

1. **过程可追溯**：通过 Git 历史和阶段记录说明 AI 参与了需求拆解、实现、修复、重构、验证和文档沉淀。
2. **协作可复用**：将经验沉淀为 Spec、Rules、AI 编程 Skills 和 Prompt 模板，而不是一次性对话。
3. **自审可说明**：记录如何使用 Computer Use / Browser 进行页面自检、点击验证、截图复盘和真实用户体验检查。
4. **产物可验证**：仓库、文档、部署预览、工作台入口和核心代码路径都有明确索引。
5. **人机分工清晰**：人类负责人负责目标判断、产品取舍和体验验收；Codex 负责实现、排查、重构、验证和文档整理。

## 当前仓库信息

- 仓库：`https://github.com/jiajiajiaxr/bottled-water`
- 主工程目录：`AgentHub`
- 主要技术栈：React 18 + TypeScript + Vite + Ant Design；FastAPI + SQLAlchemy + Alembic；WebSocket/SSE；Tool / Skill / MCP；uv + pnpm。
