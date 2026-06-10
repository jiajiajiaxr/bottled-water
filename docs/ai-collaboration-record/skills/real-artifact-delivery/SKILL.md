---
name: real-artifact-delivery
description: Use this skill when AgentHub must generate, preview, download, deploy, or audit real artifacts such as PDF, DOCX, PPTX, XLSX, HTML, project files, or deployment URLs. It prevents fake preview cards, fake deployment states, and text-only claims of completion.
---

# Real Artifact Delivery

## Purpose

Use this skill whenever a user asks AgentHub to produce a file, web page, project, document, preview, or deployment. The standard is not "the agent said it finished"; the standard is a real persisted artifact that the user can open, download, or run.

## Success Invariants

For generated artifacts:

1. A backend tool actually ran.
2. `ToolInvocation` or equivalent run record exists.
3. `Artifact` or file record is persisted.
4. `preview_card` message contains a real `artifact_id`.
5. `preview_url` opens the actual preview.
6. `export_url` downloads the real generated format.
7. Refreshing the conversation still shows the card.

For deployed artifacts:

1. Deployment state has a real deployment id.
2. The URL is reachable or has a clear failure reason.
3. The preview page is not blank.
4. The deployment record survives refresh.

## Anti-patterns

- Returning "已生成" without creating a file.
- Showing a card whose `artifact_id` is missing or invalid.
- Marking deployment as `deployed` without a reachable URL.
- Using a fixed fallback template unrelated to the user request.
- Downloading `index.html` when the artifact is DOCX/PDF/PPTX/XLSX.

## Workflow

1. Determine the requested output format and delivery mode.
2. Verify the current agent has permission to call the relevant tool.
3. Ensure the model/tool path creates real files, not only text.
4. Map tool result to chat-visible card only after successful tool execution.
5. Keep the assistant's natural reply separate from the artifact card.
6. Verify preview, export, and refresh recovery.

## Good Prompt Shape

```text
用户要求生成产物时，不允许只用文字说明完成。
必须调用对应 artifact/file/deploy 工具，并返回真实 artifact_id、preview_url、export_url。
如果工具失败，不创建卡片，给出明确失败原因。
```

## Acceptance

The artifact is acceptable only when the user can click it in chat, see a meaningful preview, download the correct file type, and find the file again from workspace files.
