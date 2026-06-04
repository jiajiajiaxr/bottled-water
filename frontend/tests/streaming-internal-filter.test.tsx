import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useStreamingMessages } from "../src/hooks/useStreamingMessages";

describe("useStreamingMessages internal block filtering", () => {
  it("filters status_report fragments from streamed thinking text", () => {
    const { result } = renderHook(() => useStreamingMessages("conversation-1"));

    act(() => {
      result.current.streamHandlers.onMessageStart({
        agent_id: "agent-1",
        agent_message_id: "message-1",
        agent_name: "Daily Chat Agent",
      });
    });

    act(() => {
      result.current.streamHandlers.onThinking?.("agent-1", "visible thinking\n``");
    });

    expect(result.current.streamingMessages.get("agent-1")?.thinking).toBe(
      "visible thinking",
    );

    act(() => {
      result.current.streamHandlers.onThinking?.(
        "agent-1",
        '`status_report\n{"state":"completed"}\n```\nvisible conclusion',
      );
    });

    expect(result.current.streamingMessages.get("agent-1")?.thinking).toBe(
      "visible thinking\nvisible conclusion",
    );
  });
});
