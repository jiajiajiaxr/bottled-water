import React from "react";
import { App as AntApp } from "antd";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { api } from "../src/api";
import { ExternalAgentsPanel } from "../src/features/settings/components/ExternalAgentsPanel";

vi.mock("../src/api", () => ({
  api: {
    externalAgentProbe: vi.fn(),
    reprobeExternalAgent: vi.fn(),
    externalAgentRuns: vi.fn(),
  },
}));

describe("ExternalAgentsPanel", () => {
  it("shows installed and degraded providers", async () => {
    vi.mocked(api.externalAgentProbe).mockResolvedValue({
      providers: [
        {
          provider: "codex",
          installed: true,
          command_source: "env:CODEX_CLI_PATH",
          capabilities: ["code_edit"],
        },
        {
          provider: "claude_code",
          installed: false,
          reason: "command_not_found",
          command_source: "PATH",
          setup_hint: "Install Claude Code CLI",
          capabilities: [],
        },
      ],
      degraded: [],
    });
    vi.mocked(api.externalAgentRuns).mockResolvedValue([]);

    renderPanel();

    expect(await screen.findByText("Codex CLI")).toBeInTheDocument();
    expect(screen.getByText("Claude Code CLI")).toBeInTheDocument();
    expect(screen.getByText("OpenCode CLI")).toBeInTheDocument();
    expect(screen.getByText("可用")).toBeInTheDocument();
    expect(screen.getAllByText("降级").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText(/Install Claude Code CLI/)).toBeInTheDocument();
  });

  it("can reprobe a provider", async () => {
    vi.mocked(api.externalAgentProbe).mockResolvedValue({
      providers: [
        {
          provider: "codex",
          installed: false,
          reason: "command_not_found",
          setup_hint: "Install Codex",
        },
      ],
      degraded: [],
    });
    vi.mocked(api.externalAgentRuns).mockResolvedValue([]);
    vi.mocked(api.reprobeExternalAgent).mockResolvedValue({
      providers: [
        {
          provider: "codex",
          installed: true,
          command_source: "env:CODEX_CLI_PATH",
          capabilities: ["code_edit"],
        },
      ],
      degraded: [],
    });

    renderPanel();

    const buttons = await screen.findAllByText("重新探测");
    fireEvent.click(buttons[0]);

    await waitFor(() =>
      expect(api.reprobeExternalAgent).toHaveBeenCalledWith("codex"),
    );
    expect(
      await screen.findByText("已通过环境变量配置（路径已隐藏）"),
    ).toBeInTheDocument();
    expect(screen.queryByText("C:/tools/codex.exe")).not.toBeInTheDocument();
  });
});

function renderPanel() {
  return render(
    <AntApp>
      <ExternalAgentsPanel />
    </AntApp>,
  );
}
