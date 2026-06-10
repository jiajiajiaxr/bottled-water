---
name: ai-product-owner-briefing
description: Use this skill when turning vague product feedback, screenshots, review criteria, or demo expectations into concrete AgentHub engineering tasks. It helps Codex preserve the human product owner's intent while translating it into scoped implementation work.
---

# AI Product Owner Briefing

## Purpose

Use this skill when the human owner provides high-level product direction, screenshots, or evaluation requirements. The skill turns that feedback into actionable engineering work without losing the original product judgment.

## Inputs

- User feedback in natural language.
- Screenshots showing UI mismatch, missing behavior, or poor experience.
- Review rubrics such as "AI 协作能力 30%".
- Demo goals such as "答辩演示可用", "像商业级平台", or "不要玩具 Demo".
- Existing docs and Git history.

## Workflow

1. Extract the user-visible goal.
2. Separate product requirement, engineering requirement, and acceptance criterion.
3. Identify whether the change belongs to frontend, backend, runtime, docs, or packaging.
4. Keep the user's examples as signals, not as the full requirement boundary.
5. Convert the goal into a small number of executable tasks.
6. Preserve tradeoffs and explicit non-goals.

## Prompt Pattern

```text
请把这段产品反馈转成工程任务：
1. 用户真正想改善的体验是什么？
2. 哪些是必须做的闭环？
3. 哪些只是举例？
4. 前端、后端、文档分别要改哪里？
5. 验收时用户应该看到什么？
```

## Acceptance

The output should make it clear:

- What problem is being solved.
- Why it matters for demo or product maturity.
- Which files/modules are likely involved.
- What "done" means from the user's perspective.
