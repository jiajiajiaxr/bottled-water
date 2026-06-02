// @vitest-environment jsdom

import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import { LandingPage } from "../src/pages/LandingPage";

describe("LandingPage", () => {
  it("renders the product release page with core sections", () => {
    render(
      <MemoryRouter>
        <LandingPage />
      </MemoryRouter>,
    );

    expect(screen.getByRole("heading", { name: "AgentHub 多智能体协作工作台" })).toBeTruthy();
    expect(screen.getByText("会话协作")).toBeTruthy();
    expect(screen.getByText("从一句需求到真实产物的闭环")).toBeTruthy();
    expect(screen.getByText("为多 Agent Function Call 工作流准备的分层架构")).toBeTruthy();
    expect(screen.getByText("沙箱运行 Python")).toBeTruthy();
    expect(screen.getAllByText("查看 GitHub").length).toBeGreaterThan(0);
  });
});
