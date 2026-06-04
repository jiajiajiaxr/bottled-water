import { describe, expect, it } from "vitest";

import { stripInternalAgentOutput } from "./message";

describe("stripInternalAgentOutput", () => {
  it("removes complete status_report fenced blocks", () => {
    const text = [
      "visible answer",
      "``` status_report",
      '{"state":"completed"}',
      "```",
      "final answer",
    ].join("\n");

    expect(stripInternalAgentOutput(text)).toBe("visible answer\nfinal answer");
  });

  it("keeps streaming status_report fence prefixes hidden", () => {
    expect(stripInternalAgentOutput("visible answer\n``` sta")).toBe(
      "visible answer",
    );
    expect(stripInternalAgentOutput("visible answer\n``` status")).toBe(
      "visible answer",
    );
  });

  it("removes status fence aliases", () => {
    const text = [
      "visible answer",
      "```status",
      '{"state":"completed"}',
      "```",
      "final answer",
    ].join("\n");

    expect(stripInternalAgentOutput(text)).toBe("visible answer\nfinal answer");
  });
});
