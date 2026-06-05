import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { MarkdownContent } from "./markdown";

describe("MarkdownContent", () => {
  it("does not render streaming status_report fences as code blocks", () => {
    const { container } = render(
      <MarkdownContent
        text={
          'visible answer\n```status_report\n{"state":"completed","will":"complete"}'
        }
      />,
    );

    expect(screen.getByText("visible answer")).toBeTruthy();
    expect(container.querySelector("pre")).toBeNull();
    expect(container.textContent).not.toContain("status_report");
    expect(container.textContent).not.toContain('"state"');
  });

  it("keeps completed normal code blocks visible", () => {
    const { container } = render(
      <MarkdownContent text={"visible answer\n```python\nprint(1)\n```"} />,
    );

    expect(screen.getByText("visible answer")).toBeTruthy();
    expect(container.querySelector("pre")?.textContent).toContain("print(1)");
  });

  it("renders streaming unfinished code fences without waiting for closure", () => {
    render(
      <MarkdownContent text={"visible answer\n```python\nprint(1)"} />,
    );

    expect(screen.getByText("visible answer")).toBeTruthy();
    expect(screen.getByTestId("markdown-code-block").textContent).toContain("print(1)");
    expect(screen.getByText("生成中")).toBeTruthy();
  });

  it("runs runnable code blocks and renders sandbox result inline", async () => {
    const onRunCode = vi.fn(async () => ({
      status: "succeeded",
      stdout: "hello\n",
      stderr: "",
      exit_code: 0,
      duration_ms: 12,
    }));
    render(
      <MarkdownContent
        text={"```python\nprint('hello')\n```"}
        onRunCode={onRunCode}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "运行" }));

    await waitFor(() => expect(onRunCode).toHaveBeenCalledWith(0, "python", "print('hello')"));
    expect((await screen.findByTestId("code-run-result")).textContent).toContain("执行成功");
    expect(screen.getByTestId("code-run-result").textContent).toContain("hello");
  });
});
