import { describe, expect, it, vi } from "vitest";
import { streamAssistantReply } from "../src/api/message";

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
});
