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
        name: "AgentHub 多 Agent 协作平台文档",
      }),
    ).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "打开控制台" })).toHaveLength(2);
    expect(screen.queryByText("联系我们")).not.toBeInTheDocument();
    expect(screen.queryByText("Demo Plan ↗")).not.toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "演示链路" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "选择你的阅读路径" }),
    ).toBeInTheDocument();
    expect(screen.getByText("从会话到产物")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "产品平台总览" }),
    ).toBeInTheDocument();
    expect(screen.getAllByText("本地启动").length).toBeGreaterThan(0);
    expect(
      screen.getByRole("heading", { name: "平台能力地图" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "模型与运行模式" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "工作流节点说明" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "API 总览" })).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "文件、知识库与产物生命周期" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "常见问题与排查入口" }),
    ).toBeInTheDocument();
  });

  it("filters sidebar links from the search input", () => {
    render(
      <MemoryRouter>
        <DocsPage />
      </MemoryRouter>,
    );

    const sidebar = screen.getByLabelText("文档目录");
    fireEvent.change(within(sidebar).getByLabelText("搜索文档"), {
      target: { value: "沙箱" },
    });

    expect(within(sidebar).getByText("沙箱执行")).toBeInTheDocument();
    expect(within(sidebar).queryByText("首次会话")).not.toBeInTheDocument();
  });

  it("removes the announcement sticky offset after closing the banner", () => {
    const { container } = render(
      <MemoryRouter>
        <DocsPage />
      </MemoryRouter>,
    );

    const shell = screen.getByRole("main");
    const closeButton = container.querySelector<HTMLButtonElement>(
      ".docs-announcement button",
    );
    if (!closeButton) throw new Error("Missing docs announcement close button");

    expect(shell).toHaveClass("docs-shell-announced");
    fireEvent.click(closeButton);

    expect(container.querySelector(".docs-announcement")).not.toBeInTheDocument();
    expect(shell).toHaveClass("docs-shell-plain");
  });
});
