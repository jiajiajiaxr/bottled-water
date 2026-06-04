import { describe, expect, it } from "vitest";
import { stripInternalAgentOutput } from "../src/lib/message";

describe("stripInternalAgentOutput", () => {
  it("removes completed status_report fenced blocks", () => {
    const text = [
      "visible preface",
      "```status_report",
      "{",
      '  "state": "completed",',
      '  "confidence": 0.95',
      "}",
      "```",
      "visible answer",
    ].join("\n");

    expect(stripInternalAgentOutput(text)).toBe(
      "visible preface\nvisible answer",
    );
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
    expect(stripInternalAgentOutput("visible answer\n``")).toBe(
      "visible answer",
    );
    expect(stripInternalAgentOutput("```sta")).toBe("");
    expect(stripInternalAgentOutput("visible answer\n```status")).toBe(
      "visible answer",
    );
  });

  it("removes status_report fences that include spacing after backticks", () => {
    const text = [
      "visible answer",
      "``` status_report",
      '{"state":"completed"}',
      "```",
      "later answer",
    ].join("\n");

    expect(stripInternalAgentOutput(text)).toBe("visible answer\nlater answer");
  });

  it("removes status report shaped generic fenced blocks", () => {
    const text = [
      "visible answer",
      "```json",
      '{"state":"completed","will":"complete","confidence":0.95}',
      "```",
      "later answer",
    ].join("\n");

    expect(stripInternalAgentOutput(text)).toBe("visible answer\nlater answer");
  });

  it("hides generic opening fences while streaming", () => {
    expect(stripInternalAgentOutput("visible answer\n```\nstatus_report")).toBe(
      "visible answer",
    );
    expect(
      stripInternalAgentOutput(
        'visible answer\n```\n{"state":"completed","will":"complete"}',
      ),
    ).toBe("visible answer");
  });

  it("keeps normal completed code blocks", () => {
    const text = ["visible answer", "```python", "print(1)", "```"].join("\n");

    expect(stripInternalAgentOutput(text)).toBe(text);
  });
});
