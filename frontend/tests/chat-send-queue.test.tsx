import { App as AntApp } from "antd";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ChatPanel } from "../src/features/chat/components/ChatPanel";
import { useConversationStore, useMessageStore } from "../src/store";
import type { Conversation } from "../src/types";

const sendMock = vi.fn();
const cancelMock = vi.fn();

vi.mock("@/api", () => ({
  api: {
    modelConfigs: vi.fn().mockResolvedValue([]),
    workspaceFileTree: vi.fn().mockResolvedValue({ root: { type: "folder", children: [] } }),
  },
}));

vi.mock("@/hooks", () => ({
  useMessageOperations: () => ({
    send: sendMock,
    cancel: cancelMock,
    streamingMessages: new Map(),
    displayOrder: [],
  }),
}));

describe("ChatPanel queued sending", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    sendMock.mockReset();
    cancelMock.mockReset();
    sendMock.mockResolvedValue(undefined);
    useMessageStore.getState().setMessagesForConversation("conversation-1", []);
    useConversationStore.setState({
      activeId: "conversation-1",
      conversations: [conversation("running")],
      activeConversation: conversation("running"),
      localRunningConversationIds: new Set(["conversation-1"]),
    });
  });

  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
  });

  it("queues user input while the current response is running and sends it after idle", async () => {
    const { rerender } = renderPanel(conversation("running"));

    typeMessage("queued follow-up");
    fireEvent.click(screen.getByTestId("send-message"));

    expect(sendMock).not.toHaveBeenCalled();
    expect(screen.getByTestId("composer-send-queue").textContent).toContain(
      "queued follow-up",
    );

    await act(async () => {
      useConversationStore.setState({
        conversations: [conversation("idle")],
        activeConversation: conversation("idle"),
        localRunningConversationIds: new Set(),
      });
      rerender(wrap(conversation("idle")));
    });

    await act(async () => {
      vi.advanceTimersByTime(180);
      await Promise.resolve();
    });

    expect(sendMock).toHaveBeenCalledTimes(1);
    expect(sendMock.mock.calls[0][0]).toBe("queued follow-up");
  });

  it("frees queue capacity immediately after dispatching a queued input", async () => {
    const { rerender } = renderPanel(conversation("running"));

    for (const value of ["one", "two", "three", "four", "five"]) {
      typeMessage(value);
      fireEvent.click(screen.getByTestId("send-message"));
    }

    expect(screen.getByTestId("composer-send-queue").textContent).toContain("5/5");

    await act(async () => {
      useConversationStore.setState({
        conversations: [conversation("idle")],
        activeConversation: conversation("idle"),
        localRunningConversationIds: new Set(),
      });
      rerender(wrap(conversation("idle")));
    });

    await act(async () => {
      vi.advanceTimersByTime(180);
      await Promise.resolve();
    });

    expect(sendMock).toHaveBeenCalledTimes(1);
    expect(sendMock.mock.calls[0][0]).toBe("one");
    expect(screen.getByTestId("composer-send-queue").textContent).toContain("4/5");

    typeMessage("six");
    fireEvent.click(screen.getByTestId("send-message"));

    const queueText = screen.getByTestId("composer-send-queue").textContent;
    expect(queueText).toContain("5/5");
    expect(queueText).toContain("six");
  });
});

function renderPanel(active: Conversation) {
  return render(wrap(active));
}

function wrap(active: Conversation) {
  return (
    <AntApp>
      <ChatPanel active={active} loading={false} userName="User" />
    </AntApp>
  );
}

function typeMessage(value: string) {
  fireEvent.change(screen.getByRole("textbox"), { target: { value } });
}

function conversation(status: string): Conversation {
  return {
    id: "conversation-1",
    chat_type: "single",
    title: "Daily Chat Agent",
    participants: [],
    updatedAt: "2026-06-07T00:00:00.000Z",
    pinned: false,
    archived: false,
    unread: 0,
    tags: [],
    lastMessage: "",
    generation_status: status,
  };
}
