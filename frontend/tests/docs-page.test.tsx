import React from "react";
import { describe, expect, it } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { DocsPage } from "../src/pages/DocsPage";

describe("DocsPage", () => {
  it("renders the AgentHub documentation landing content", () => {
    render(
      <MemoryRouter>
        <DocsPage />
      </MemoryRouter>,
    );

    expect(
      screen.getByRole("heading", {
        name: "AgentHub 多 Agent 协作平台说明文档",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "演示链路" }),
    ).toBeInTheDocument();
    expect(screen.getAllByText("本地启动").length).toBeGreaterThan(0);
  });

  it("filters sidebar links from the search input", () => {
    render(
      <MemoryRouter>
        <DocsPage />
      </MemoryRouter>,
    );

    const sidebar = screen.getByLabelText("文档目录");
    fireEvent.change(within(sidebar).getByLabelText("搜索文档"), {
      target: { value: "部署" },
    });

    expect(within(sidebar).getByText("部署预览")).toBeInTheDocument();
    expect(within(sidebar).queryByText("首次登录")).not.toBeInTheDocument();
  });
});
