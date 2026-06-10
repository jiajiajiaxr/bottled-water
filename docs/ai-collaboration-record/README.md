# AgentHub AI 协作开发记录包

> 用途：作为仓库内可追溯的 AI 协作资产，也可作为飞书文档、答辩展示和项目复盘的材料来源。

本目录记录 AgentHub 从需求理解、架构设计、编码实现、缺陷修复、体验验收到发布包装的 AI 协作过程。它重点证明：项目不是只“用了 AI 生成代码”，而是在持续的人机协作中形成了可复用的 Spec、Rules、Skills、Prompt 和工程交付方法。

## 文件说明

| 文件 | 作用 |
| --- | --- |
| [00-feishu-doc-outline.md](./00-feishu-doc-outline.md) | 可复制到飞书文档的对外说明模板 |
| [01-collaboration-log.md](./01-collaboration-log.md) | 基于真实 Git 历史整理的 AI 协作开发过程记录 |
| [02-ai-collaboration-spec.md](./02-ai-collaboration-spec.md) | AI 协作 Spec：任务输入、验收口径、交付边界 |
| [03-agent-rules.md](./03-agent-rules.md) | AI 协作 Rules：代码、权限、安全、提交和产物规则 |
| [04-skills-and-prompts.md](./04-skills-and-prompts.md) | 高级 Skills / Prompts：角色技能、调度协议、复盘模板 |
| [05-artifact-index.md](./05-artifact-index.md) | 产物地址索引：仓库、文档、运行入口、演示链路 |

## 证明重点

1. **过程可追溯**：通过 Git 历史和阶段记录说明 AI 参与了需求拆解、实现、修复、重构和文档沉淀。
2. **规范可复用**：将协作经验沉淀为 Spec、Rules、Skills 和 Prompt 模板。
3. **产物可验证**：仓库、文档、部署预览、工作台入口和核心代码路径都有明确索引。
4. **人机分工清晰**：人类负责人负责目标判断、产品取舍和体验验收；AI 负责实现、排查、重构、验证和整理。


## 当前仓库信息

- 仓库：`https://github.com/jiajiajiaxr/bottled-water`
- 主工程目录：`AgentHub`
- 主要技术栈：React 18 + TypeScript + Vite + Ant Design；FastAPI + SQLAlchemy + Alembic；WebSocket/SSE；Tool / Skill / MCP；uv + pnpm。

