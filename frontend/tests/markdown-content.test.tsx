import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MarkdownContent } from "../src/lib/markdown";

describe("MarkdownContent", () => {
  it("does not render internal status_report fences as code blocks", () => {
    const { container } = render(
      <MarkdownContent
        text={[
          "可见回答",
          "```status_report",
          '{"state":"completed","will":"complete"}',
          "```",
          "继续说明",
        ].join("\n")}
      />,
    );

    expect(screen.getByText(/可见回答/)).toBeInTheDocument();
    expect(screen.getByText(/继续说明/)).toBeInTheDocument();
    expect(container.querySelector("pre")).toBeNull();
    expect(screen.queryByText(/status_report/)).not.toBeInTheDocument();
  });
});
