import React from "react";
import { App as AntApp } from "antd";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { api } from "../src/api";
import { AgentDirectoryDrawer } from "../src/features/agents/components/AgentDirectoryDrawer";
import type { Agent } from "../src/types";

vi.mock("../src/api", () => ({
  api: {
    modelConfigs: vi.fn(),
    tools: vi.fn(),
    skills: vi.fn(),
    mcpServers: vi.fn(),
  },
}));

const agent: Agent = {
  id: "agent-1",
  name: "Writing Agent",
  type: "writing",
  version: "1.0.0",
  capabilities: [{ label: "写作", category: "文档", proficiency: 5 }],
  description: "生成正式文档",
  status: "online",
  provider: "official",
  is_official: true,
  response_latency_ms: 0,
  config: {
    tools: ["file.extract_text", "legacy.missing_tool"],
    skill_ids: [],
    mcp_server_ids: [],
  },
};

describe("AgentDirectoryDrawer asPage", () => {
  it("loads capability catalogs and preserves legacy selected tools", async () => {
    vi.mocked(api.modelConfigs).mockResolvedValue([
      {
        id: "model-1",
        name: "豆包",
        model_id: "doubao",
        provider_id: "p1",
        purpose: "chat",
        context_window: 128000,
        max_output_tokens: 8192,
        temperature_default: 0.7,
        status: "active",
      },
    ]);
    vi.mocked(api.tools).mockResolvedValue([
      {
        id: "tool-1",
        name: "file.extract_text",
        display_name: "提取文本",
        description: "提取文件文本",
        category: "file",
        type: "builtin",
        status: "active",
        version: "1.0.0",
        input_schema: {},
        output_schema: {},
        permissions: [],
        implementation: {},
        runtime: {},
        tags: [],
        config: {},
        is_builtin: true,
      },
    ]);
    vi.mocked(api.skills).mockResolvedValue([]);
    vi.mocked(api.mcpServers).mockResolvedValue([]);

    render(
      <AntApp>
        <AgentDirectoryDrawer
          asPage
          agents={[agent]}
          onClose={vi.fn()}
          onRefresh={vi.fn()}
          onCreateAgent={vi.fn()}
          onUpdateAgent={vi.fn()}
          onDeleteAgent={vi.fn(async () => undefined)}
          onTestAgent={vi.fn(async () => "ok")}
        />
      </AntApp>,
    );

    await waitFor(() => expect(api.tools).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByTestId("edit-agent-agent-1"));

    expect(await screen.findByText("提取文本 · file.extract_text")).toBeInTheDocument();
    expect(screen.getByText("旧配置：legacy.missing_tool")).toBeInTheDocument();
  });
});
