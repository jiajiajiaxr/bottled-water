---
name: architecture-debt-review
description: Use this skill when reviewing AgentHub for architectural debt, duplicated logic, legacy entry points, oversized files, or unclear service boundaries. It helps Codex act as an engineering reviewer rather than only an implementer.
---

# Architecture Debt Review

## Purpose

Use this skill before or after larger changes to make sure the project does not regress into large files, duplicated runtime paths, fake shims, or mixed domain responsibilities.

## Review Targets

- Deprecated entry points that still contain business logic.
- Services that mix protocol, execution, persistence, and UI mapping.
- Repeated tool-result-to-message mapping.
- Repeated workflow or chat runtime decisions.
- Large frontend components holding routing, state, rendering, and API logic together.
- Docs that describe a newer architecture while code still uses an older one.

## Review Questions

1. Is this logic in the right domain?
2. Is the old entry point only a shim?
3. Is the dependency direction clean?
4. Is behavior duplicated in old and new paths?
5. Can a future developer find the feature from file names?
6. Does the documentation match the actual code?

## Prompt Pattern

```text
请从架构负责人视角审查这次改动：
找出重复逻辑、旧入口残留、职责混杂、过长文件和文档不一致。
只给出影响后续维护的真实问题，不做无关重构建议。
```

## Acceptance

The review is useful when it produces concrete file-level findings and tells whether to fix now, document as risk, or leave unchanged.
