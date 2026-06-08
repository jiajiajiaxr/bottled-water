# AgentHub Frontend

React frontend for the AgentHub IM workbench.

## Stack

- React 18
- TypeScript
- Vite
- Ant Design 5
- Zustand
- SCSS
- Vitest and Testing Library

## Layout

```text
frontend/
  src/
    api/              API client, SSE, WebSocket, domain wrappers
    features/         chat, agents, workflow, preview, platform, auth, files
    hooks/            shared workflow/message hooks
    lib/              pure utilities and render helpers
    pages/            route-level pages
    router/           React Router setup
    store/            Zustand stores
    styles/           SCSS partials
    types/            domain types
    utils/            frontend utilities
  tests/              Vitest tests
```

## Local Run

```powershell
pnpm install
pnpm dev
```

Open `http://localhost:5173`.

## Build And Test

```powershell
pnpm build
pnpm exec vitest run --config tests/vitest.config.ts
```

Targeted workflow checks:

```powershell
pnpm exec vitest run tests/workflow-board-panel.test.tsx tests/workflow-studio.test.tsx tests/workflow-utils.test.ts --config tests/vitest.config.ts
```

## Important Surfaces

- `src/pages/WorkbenchPage`: main app shell.
- `src/features/chat`: conversation sidebar, chat panel, message bubbles, drawers.
- `src/features/agents`: agent directory and configuration.
- `src/features/platform`: tools, skills, MCP, workflow, security, and other platform panels.
- `src/features/workflow`: embedded workflow studio and canvas utilities.
- `src/features/preview`: artifact preview/edit/diff/deployment panel.
- `src/features/workspaceFiles`: workspace file tree and file preview flows.
- `src/api/message.ts`: streaming message send/merge logic.
- `src/api/websocket.ts`: WebSocket connection manager.

## Notes

- The API base is `/api/v1`.
- WebSocket paths are `/ws` and `/ws/conversations/{id}`.
- Do not put real model provider secrets in frontend code or environment values.
