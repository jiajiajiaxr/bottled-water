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

  it("never exposes status_report while a fence streams character by character", () => {
    const raw =
      'visible answer\n```status_report\n{"state":"completed","will":"complete","confidence":0.95}\n```\nfinal answer';
    let accumulated = "";

    for (const char of raw) {
      accumulated += char;
      const visible = stripInternalAgentOutput(accumulated);
      expect(visible).not.toContain("status_report");
      expect(visible).not.toContain('"state"');
      expect(visible).not.toContain("```");
    }

    expect(stripInternalAgentOutput(raw)).toBe("visible answer\nfinal answer");
  });

  it("hides streaming generic json fences shaped like status reports", () => {
    const text = [
      "visible answer",
      "```json",
      '{"state":"completed","will":"complete","rationale":"done"}',
    ].join("\n");

    expect(stripInternalAgentOutput(text)).toBe("visible answer");
  });
});
