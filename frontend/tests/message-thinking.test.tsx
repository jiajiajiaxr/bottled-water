import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MessageBubble } from "../src/features/chat/components/MessageBubble";
import type { ChatMessage } from "../src/types";

describe("MessageBubble thinking content", () => {
  it("does not show a thinking placeholder without real thinking text", () => {
    const { container } = render(
      <MessageBubble
        message={assistantMessage({
          content: "answer",
          rawContent: {
            thinking_enabled: true,
            _streamThinkingEnabled: true,
          },
          streamState: "streaming",
          status: "streaming",
        })}
        onCopy={() => undefined}
        onPreview={() => undefined}
        onQuote={() => undefined}
      />,
    );

    expect(screen.queryByText(/思考中/)).not.toBeInTheDocument();
    expect(container.querySelector(".thinking-block")).toBeNull();
  });

  it("still shows the thinking block when real thinking text exists", () => {
    const { container } = render(
      <MessageBubble
        message={assistantMessage({
          thinking: "real reasoning",
          rawContent: {
            thinking_enabled: true,
          },
        })}
        onCopy={() => undefined}
        onPreview={() => undefined}
        onQuote={() => undefined}
      />,
    );

    expect(container.querySelector(".thinking-block")).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /思考过程/ }));
    expect(screen.getByText("real reasoning")).toBeInTheDocument();
  });
});

function assistantMessage(overrides: Partial<ChatMessage>): ChatMessage {
  return {
    id: "assistant-1",
    conversationId: "conversation-1",
    role: "assistant",
    kind: "text",
    author: "Daily Chat Agent",
    content: "",
    rawContent: {},
    createdAt: "2026-06-08T04:00:00.000Z",
    state: "active",
    ...overrides,
  };
}
