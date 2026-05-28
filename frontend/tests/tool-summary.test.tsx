import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MessageBubble } from "../src/features/chat/components/MessageBubble";
import { summarizeToolEvents } from "../src/lib/toolEvents";
import type { ChatMessage } from "../src/types";

describe("tool call summary", () => {
  it("deduplicates repeated sandbox calls", () => {
    const summary = summarizeToolEvents([
      { toolName: "sandbox.run", toolCallId: "1", status: "succeeded" },
      { toolName: "sandbox.run", toolCallId: "2", status: "succeeded" },
      { toolName: "sandbox.run", toolCallId: "3", status: "succeeded" },
    ]);

    expect(summary?.label).toBe("调用：sandbox.run ×3");
  });

  it("renders the summary next to message actions", () => {
    render(
      <MessageBubble
        message={messageWithTools([
          { tool_name: "sandbox.run", tool_call_id: "1", status: "succeeded" },
          { tool_name: "sandbox.run", tool_call_id: "2", status: "succeeded" },
          { tool_name: "sandbox.run", tool_call_id: "3", status: "succeeded" },
        ])}
        onCopy={() => undefined}
        onPreview={() => undefined}
        onQuote={() => undefined}
        onRegenerate={() => undefined}
      />,
    );

    expect(screen.getByTestId("message-tool-summary")).toHaveTextContent(
      "调用：sandbox.run ×3",
    );
  });

  it("uses warning tone for failed tools", () => {
    render(
      <MessageBubble
        message={messageWithTools([
          {
            tool_name: "sandbox.run",
            tool_call_id: "failed-1",
            status: "failed",
            stderr: "blocked command",
          },
        ])}
        onCopy={() => undefined}
        onPreview={() => undefined}
        onQuote={() => undefined}
        onRegenerate={() => undefined}
      />,
    );

    const summary = screen.getByTestId("message-tool-summary");
    expect(summary).toHaveTextContent("工具失败：sandbox.run");
    expect(summary).toHaveClass("warning");
  });
});

function messageWithTools(toolEvents: Array<Record<string, unknown>>): ChatMessage {
  return {
    id: "assistant-1",
    conversationId: "conversation-1",
    role: "assistant",
    kind: "text",
    author: "Frontend Worker",
    content: "done",
    rawContent: { text: "done", tool_events: toolEvents },
    createdAt: "2026-05-28T00:00:00.000Z",
  };
}
