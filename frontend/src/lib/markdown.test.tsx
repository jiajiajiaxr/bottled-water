import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

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
});
