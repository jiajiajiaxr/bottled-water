import { describe, expect, it } from "vitest";
import { stripInternalAgentOutput } from "../src/lib/message";

describe("stripInternalAgentOutput", () => {
  it("removes completed status_report fenced blocks", () => {
    const text = [
      "前置说明",
      "```status_report",
      "{",
      '  "state": "completed",',
      '  "confidence": 0.95',
      "}",
      "```",
      "可见回答",
    ].join("\n");

    expect(stripInternalAgentOutput(text)).toBe("前置说明\n可见回答");
  });

  it("hides partial streaming status_report fenced blocks", () => {
    const text = [
      "```status_report",
      "{",
      '  "state": "completed"',
    ].join("\n");

    expect(stripInternalAgentOutput(text)).toBe("");
  });

  it("hides split status_report fence prefixes while streaming", () => {
    expect(stripInternalAgentOutput("```")).toBe("");
    expect(stripInternalAgentOutput("```sta")).toBe("");
    expect(stripInternalAgentOutput("可见回答\n```status")).toBe("可见回答");
  });
});
