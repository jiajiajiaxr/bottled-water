import { describe, expect, it, vi } from "vitest";
import { sendMessageWs, streamAssistantReply } from "../src/api/message";

class FakeEventSource {
  static latest?: FakeEventSource;

  listeners = new Map<string, Array<(event: MessageEvent) => void>>();

  closed = false;

  constructor(public url: string) {
    FakeEventSource.latest = this;
  }

  addEventListener(type: string, listener: (event: MessageEvent) => void) {
    this.listeners.set(type, [...(this.listeners.get(type) ?? []), listener]);
  }

  close() {
    this.closed = true;
  }

  emit(type: string, payload: Record<string, unknown>) {
    const event = new MessageEvent(type, { data: JSON.stringify(payload) });
    (this.listeners.get(type) ?? []).forEach((listener) => listener(event));
  }
}

class FakeWebSocket {
  static latest?: FakeWebSocket;

  static OPEN = 1;

  readyState = FakeWebSocket.OPEN;

  onopen: (() => void) | null = null;

  onmessage: ((event: MessageEvent) => void) | null = null;

  onclose: (() => void) | null = null;

  onerror: (() => void) | null = null;

  sent: string[] = [];

  constructor(public url: string) {
    FakeWebSocket.latest = this;
    window.setTimeout(() => this.onopen?.(), 0);
  }

  send(payload: string) {
    this.sent.push(payload);
  }

  close() {
    this.readyState = 3;
    this.onclose?.();
  }

  emit(event: string, data: unknown) {
    this.onmessage?.(
      new MessageEvent("message", {
        data: JSON.stringify({ event, data }),
      }),
    );
  }
}

describe("conversation SSE stream", () => {
  it("does not close the global stream on one agent message_stop", async () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const onDone = vi.fn();
    const promise = streamAssistantReply("conversation-1", { onDone });
    const source = FakeEventSource.latest!;

    source.emit("content_block_delta", {
      agent_message_id: "agent-message-1",
      delta: { type: "text_delta", text: "hello" },
    });
    source.emit("message_stop", {
      agent_message_id: "agent-message-1",
      stop_reason: "end_turn",
    });

    await Promise.resolve();
    expect(source.closed).toBe(false);
    expect(onDone).not.toHaveBeenCalled();

    source.emit("generation_finished", { reason: "workflow_completed" });
    await expect(promise).resolves.toBe("hello");
    expect(source.closed).toBe(true);
    expect(onDone).toHaveBeenCalledOnce();
  });

  it("waits for generation_finished after workflow completed", async () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const onDone = vi.fn();
    const promise = streamAssistantReply("conversation-2", { onDone });
    const source = FakeEventSource.latest!;

    source.emit("content_block_delta", {
      agent_message_id: "agent-message-2",
      delta: { type: "text_delta", text: "done" },
    });
    source.emit("workflow:completed", { status: "completed" });

    await Promise.resolve();
    expect(source.closed).toBe(false);
    expect(onDone).not.toHaveBeenCalled();

    source.emit("generation_finished", { reason: "workflow_completed" });
    await expect(promise).resolves.toBe("done");
    expect(source.closed).toBe(true);
    expect(onDone).toHaveBeenCalledOnce();
  });

  it("emits message_stop and task status events for local pending cleanup", async () => {
    vi.stubGlobal("EventSource", FakeEventSource);
    const onMessageStop = vi.fn();
    const onTaskStatusChanged = vi.fn();
    const promise = streamAssistantReply("conversation-3", {
      onMessageStop,
      onTaskStatusChanged,
    });
    const source = FakeEventSource.latest!;

    source.emit("message_stop", {
      agent_message_id: "agent-message-3",
      stop_reason: "end_turn",
    });
    source.emit("task:status_changed", {
      id: "task-1",
      conversation_id: "conversation-3",
      status: "COMPLETED",
      title: "task",
    });

    expect(onMessageStop).toHaveBeenCalledWith({
      agent_message_id: "agent-message-3",
      stop_reason: "end_turn",
    });
    expect(onTaskStatusChanged).toHaveBeenCalledWith(
      expect.objectContaining({ id: "task-1", status: "COMPLETED" }),
    );

    source.emit("generation_finished", { reason: "direct_agent_completed" });
    await expect(promise).resolves.toBeTruthy();
  });
});

describe("conversation WebSocket stream", () => {
  it("dispatches actor agent.token payloads without requiring message_start", async () => {
    vi.stubGlobal("WebSocket", FakeWebSocket);
    window.localStorage.setItem("agenthub_token", "test-token");
    const onToken = vi.fn();
    const promise = sendMessageWs(
      "conversation-token",
      { content: { text: "hello" } },
      { onToken },
    );

    await vi.waitFor(() => expect(FakeWebSocket.latest).toBeDefined());
    const ws = FakeWebSocket.latest!;
    await vi.waitFor(() => expect(ws.sent.length).toBeGreaterThan(0));
    ws.emit("agent.token", {
      conversation_id: "conversation-token",
      agent_id: "agent-1",
      agent_name: "Daily Chat Agent",
      token: "你好",
    });

    expect(onToken).toHaveBeenCalledWith(
      "agent-1",
      "你好",
      expect.objectContaining({
        conversation_id: "conversation-token",
        agent_name: "Daily Chat Agent",
      }),
    );

    ws.emit("generation_finished", {
      conversation_id: "conversation-token",
      status: "completed",
    });
    await expect(promise).resolves.toBe("ok");
  });

  it("dispatches actor agent.tool_call payloads for local progress", async () => {
    vi.stubGlobal("WebSocket", FakeWebSocket);
    window.localStorage.setItem("agenthub_token", "test-token");
    const onToolCallStart = vi.fn();
    const promise = sendMessageWs(
      "conversation-tool",
      { content: { text: "生成 PDF" } },
      { onToolCallStart },
    );

    await vi.waitFor(() => expect(FakeWebSocket.latest).toBeDefined());
    const ws = FakeWebSocket.latest!;
    await vi.waitFor(() => expect(ws.sent.length).toBeGreaterThan(0));
    ws.emit("agent.tool_call", {
      conversation_id: "conversation-tool",
      agent_id: "agent-1",
      agent_name: "Daily Chat Agent",
      tools: ["artifact.create_pdf"],
      tool_count: 1,
    });

    expect(onToolCallStart).toHaveBeenCalledWith(
      expect.objectContaining({
        conversation_id: "conversation-tool",
        agent_id: "agent-1",
        tools: ["artifact.create_pdf"],
      }),
    );

    ws.emit("generation_finished", {
      conversation_id: "conversation-tool",
      status: "completed",
    });
    await expect(promise).resolves.toBe("ok");
  });
});
