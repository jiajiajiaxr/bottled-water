---
name: deployment-preview-verification
description: Use this skill when validating AgentHub deployment preview behavior. It focuses on turning generated project files or HTML artifacts into reachable preview URLs with clear status, health checks, and failure messages.
---

# Deployment Preview Verification

## Purpose

Use this skill when an agent claims a project or page has been deployed. The goal is to verify that the deployment is real, reachable, and linked to the correct artifact or project entry.

## Verification Checklist

1. Deployment record exists.
2. Deployment URL is present.
3. URL opens without a blank page.
4. The served content matches the user's requested project.
5. Static HTML and project-directory deployments are distinguished.
6. Backend-required projects clearly state what is running and what must be started.
7. The preview card points to the correct deployment or artifact.
8. The right preview panel shows the current deployment status.

## Anti-patterns

- Saying "deployed" while showing "尚未部署".
- Returning `localhost` text that is not reachable from the UI.
- Linking to a generic or stale artifact.
- Deploying a fallback template unrelated to generated project files.
- Hiding backend startup requirements.

## Prompt Pattern

```text
请验证部署不是口头成功：
检查 deployment 记录、可访问 URL、页面内容、预览面板状态、聊天卡片和刷新恢复。
如果不能自动运行后端，请明确说明限制，并仍提供前端静态预览地址。
```

## Acceptance

A deployment is acceptable when the user can click a visible link or preview card and see the expected app, or receive a precise failure reason and next action.
