import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { api } from "../src/api";
import { MessageBubble } from "../src/features/chat/components/MessageBubble";
import type { ChatMessage } from "../src/types";

vi.mock("../src/api", () => ({
  api: {
    runMessageCodeBlock: vi.fn(),
    previewFile: vi.fn(),
  },
}));

describe("chat code block runner", () => {
  it("runs a Python code block from the message bubble and shows stdout", async () => {
    vi.mocked(api.runMessageCodeBlock).mockResolvedValue({
      status: "succeeded",
      stdout: "42\n",
      stderr: "",
      exit_code: 0,
      duration_ms: 9,
    });

    render(
      <MessageBubble
        message={messageWithCode("```python\nprint(42)\n```")}
        workspaceId="workspace-1"
        onCopy={() => undefined}
        onPreview={() => undefined}
        onQuote={() => undefined}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "运行" }));

    await waitFor(() =>
      expect(api.runMessageCodeBlock).toHaveBeenCalledWith(
        "conversation-1",
        "assistant-1",
        {
          language: "python",
          code: "print(42)",
          index: 0,
          timeout_seconds: 10,
          workspace_id: "workspace-1",
          conversation_id: "conversation-1",
          message_id: "assistant-1",
        },
      ),
    );
    expect((await screen.findByTestId("code-run-result")).textContent).toContain("42");
  });

  it("shows a visible error when the sandbox request fails", async () => {
    vi.mocked(api.runMessageCodeBlock).mockRejectedValue(new Error("sandbox offline"));

    render(
      <MessageBubble
        message={messageWithCode("```python\nprint(42)\n```")}
        workspaceId="workspace-1"
        onCopy={() => undefined}
        onPreview={() => undefined}
        onQuote={() => undefined}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "运行" }));

    expect((await screen.findByTestId("code-run-result")).textContent).toContain(
      "sandbox offline",
    );
  });
});

function messageWithCode(content: string): ChatMessage {
  return {
    id: "assistant-1",
    conversationId: "conversation-1",
    role: "assistant",
    kind: "text",
    author: "Daily Chat Agent",
    content,
    rawContent: { text: content },
    createdAt: "2026-06-05T00:00:00.000Z",
    state: "active",
  };
}
