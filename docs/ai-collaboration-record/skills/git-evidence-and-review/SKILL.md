---
name: git-evidence-and-review
description: Use this skill when documenting, reviewing, committing, or explaining AgentHub AI-assisted development. It turns git history, diffs, screenshots, docs, and verification results into credible collaboration evidence.
---

# Git Evidence And Review

## Purpose

Use this skill when preparing AgentHub for review, defense, GitHub publication, or collaboration documentation. The goal is to show not only that AI was used, but how the AI-assisted development process was controlled, reviewed, and evidenced.

## Evidence Sources

- `git log --oneline --decorate`
- `git show --stat <commit>`
- `git diff --stat`
- Screenshots from Browser or Computer Use checks.
- Docs updated alongside code.
- Test or build commands when available.
- User-reported bugs and the corresponding repair commits.

## Review Dimensions

1. Product capability: what user-visible behavior changed.
2. Architecture boundary: which module owns the logic.
3. Runtime evidence: whether it was run, clicked, previewed, or downloaded.
4. Persistence evidence: whether refresh and history recovery work.
5. Collaboration evidence: how human feedback shaped the next change.

## Commit Discipline

- Keep commits thematic.
- Do not include `.env`, local databases, logs, caches, virtual environments, or generated local artifacts.
- Pull/rebase before pushing when the remote branch may have moved.
- Mention docs-only changes as docs commits.
- If a fix intentionally avoids tests, record why in the final note.

## Good Prompt Shape

```text
请先查看 git status 和 diff，不要覆盖未提交改动。
把本次 AI 协作过程整理成可追溯证据：
涉及哪些模块、解决了什么问题、如何验证、对应哪些提交。
```

## Acceptance

The evidence package is complete when a reviewer can follow the chain:

requirement or bug -> implementation -> visible result -> verification -> commit record -> documentation.
