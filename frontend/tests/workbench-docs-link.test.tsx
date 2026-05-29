import React from "react";
import { App as AntApp } from "antd";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { WorkbenchLayout } from "../src/pages/WorkbenchPage/WorkbenchLayout";
import type { User, Workspace } from "../src/types";

vi.mock("../src/features/chat/components/ConversationSidebar", () => ({
  ConversationSidebar: () => <aside data-testid="conversation-sidebar" />,
}));

vi.mock("../src/features/chat/components/ChatPanel", () => ({
  ChatPanel: () => <section data-testid="chat-panel" />,
}));

vi.mock("../src/features/preview/components/PreviewPanel", () => ({
  PreviewPanel: () => <section data-testid="preview-panel" />,
}));

vi.mock("../src/features/workflow/WorkflowStudioContent", () => ({
  WorkflowStudioContent: () => <section data-testid="workflow-studio" />,
}));

vi.mock("../src/pages/WorkbenchPage/BackgroundTasksButton", () => ({
  BackgroundTasksButton: () => <button type="button">后台任务</button>,
}));

const user: User = {
  id: "u1",
  name: "Demo",
  role: "demo",
};

const workspace: Workspace = {
  id: "w1",
  name: "默认工作区",
  description: "",
  type: "default",
  status: "active",
  tags: [],
  member_count: 1,
  project_count: 0,
};

function renderWorkbench() {
  return render(
    <AntApp>
      <MemoryRouter initialEntries={["/app"]}>
        <Routes>
          <Route
            path="/app"
            element={
              <WorkbenchLayout
                currentUser={user}
                onLogout={vi.fn()}
                workspaces={[workspace]}
                activeWorkspace={workspace}
                activeWorkspaceId={workspace.id}
                selectWorkspace={vi.fn()}
                openMainTab={vi.fn()}
                conversations={[]}
                activeId={undefined}
                active={undefined}
                conversationCategories={[]}
                selectConversation={vi.fn()}
                setCreateOpen={vi.fn()}
                addConversationCategory={vi.fn()}
                patchConversation={vi.fn()}
                updateConversations={vi.fn()}
                setActiveId={vi.fn()}
                navigateToConversation={vi.fn()}
                messages={[]}
                loadingMessages={false}
                streamState="idle"
                send={vi.fn()}
                regenerate={vi.fn()}
                stopStreaming={vi.fn()}
                setMembersOpen={vi.fn()}
                setConversationSettingsOpen={vi.fn()}
                openWorkflowPage={vi.fn()}
                closeWorkflowPage={vi.fn()}
                workflowMode={false}
                uploadFile={vi.fn()}
                artifactPanelOpen={false}
                artifact={undefined}
                deployment={undefined}
                files={[]}
                knowledgeBases={[]}
                setArtifactPanelOpen={vi.fn()}
                saveArtifact={vi.fn()}
                deploy={vi.fn()}
                setKnowledgeBases={vi.fn()}
                openArtifactPreview={vi.fn()}
                visibleBackgroundTasks={[]}
                loadBackgroundTasks={vi.fn()}
                updateLocalRunningConversationIds={vi.fn()}
                runningConversationIds={new Set()}
              />
            }
          />
          <Route path="/docs" element={<main>文档页面</main>} />
        </Routes>
      </MemoryRouter>
    </AntApp>,
  );
}

describe("Workbench docs link", () => {
  it("navigates from the topbar to the docs page", async () => {
    renderWorkbench();

    fireEvent.click(screen.getByTestId("docs-link"));

    expect(await screen.findByText("文档页面")).toBeInTheDocument();
  });
});

