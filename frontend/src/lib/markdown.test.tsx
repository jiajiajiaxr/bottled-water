// @vitest-environment jsdom

import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { MarkdownContent } from "./markdown";

describe("MarkdownContent", () => {
  it("shows a run button for Python code blocks and renders sandbox output", () => {
    const onRunCodeBlock = vi.fn();

    render(
      <MarkdownContent
        text={"```python\nprint('hello sandbox')\n```"}
        onRunCodeBlock={onRunCodeBlock}
        codeBlockResults={{
          0: {
            status: "succeeded",
            stdout: "hello sandbox\n",
            stderr: "",
            exit_code: 0,
            duration_ms: 12,
          },
        }}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "运行" }));

    expect(onRunCodeBlock).toHaveBeenCalledWith({
      index: 0,
      language: "python",
      code: "print('hello sandbox')",
    });
    expect(screen.getByText("hello sandbox")).toBeTruthy();
    expect(screen.getByText("exit_code：0")).toBeTruthy();
  });
});

