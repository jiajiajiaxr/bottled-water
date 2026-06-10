---
name: documentation-packaging-for-review
description: Use this skill when packaging AgentHub for evaluation, GitHub release, defense, or Feishu documentation. It organizes product design, collaboration logs, architecture docs, artifact indexes, and AI collaboration evidence into a coherent review package.
---

# Documentation Packaging For Review

## Purpose

Use this skill when turning AgentHub's development work into a polished review package. The output should help a reviewer understand what the platform is, how it works, how AI collaboration was used, and where the evidence lives.

## Package Contents

- Product positioning and user journey.
- Architecture overview and runtime explanation.
- AI collaboration record.
- Skills / Prompts evidence.
- Git history and key commits.
- Artifact index and demo entry points.
- Known limitations and future work.

## Writing Standards

- Avoid generic marketing language.
- Tie every claim to a real feature, file, commit, or demo path.
- Explain human decisions and AI execution separately.
- Make the reviewer's path easy: what to read first, what to open, what to demo.
- Use clear Chinese headings and stable Markdown tables.

## Prompt Pattern

```text
请把当前项目整理成评审材料：
既说明产品能力，也说明 AI 协作开发方法。
不要写空泛宣传，要给出架构、流程、提交证据、产物地址和可复用 Skills。
```

## Acceptance

The package is ready when a reviewer can read it without project context and still understand:

- Why AgentHub exists.
- What has been implemented.
- How AI was used responsibly.
- How to verify the delivered product.
