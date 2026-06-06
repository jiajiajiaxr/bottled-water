import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { MessageBubble } from "../src/features/chat/components/MessageBubble";
import type { ChatMessage } from "../src/types";

describe("preview card interaction", () => {
  it("passes the real preview card message to the preview handler", () => {
    const onPreview = vi.fn();
    const message = previewCardMessage();

    render(
      <MessageBubble
        message={message}
        onCopy={() => undefined}
        onPreview={onPreview}
        onQuote={() => undefined}
      />,
    );

    fireEvent.click(screen.getByTestId("preview-card"));

    expect(onPreview).toHaveBeenCalledTimes(1);
    expect(onPreview).toHaveBeenCalledWith(message);
    expect(onPreview.mock.calls[0][0].rawContent.artifact_id).toBe("artifact-1");
  });
});

function previewCardMessage(): ChatMessage {
  return {
    id: "preview-message-1",
    conversationId: "conversation-1",
    role: "assistant",
    kind: "preview_card",
    author: "Master Agent",
    content: "预览产物：示例 PDF",
    rawContent: {
      artifact_id: "artifact-1",
      title: "示例 PDF",
      format: "pdf",
      media_type: "application/pdf",
      filename: "示例 PDF.pdf",
    },
    createdAt: "2026-06-05T00:00:00.000Z",
    state: "active",
    status: "completed",
  };
}
