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

  it("filters status_report fragments from streamed answer text", () => {
    const { result } = renderHook(() => useStreamingMessages("conversation-1"));

    act(() => {
      result.current.streamHandlers.onMessageStart({
        agent_id: "agent-1",
        agent_message_id: "message-1",
        agent_name: "Daily Chat Agent",
      });
    });

    act(() => {
      result.current.streamHandlers.onDelta?.("可见回答\n``", {
        agent_id: "agent-1",
        agent_message_id: "message-1",
      });
    });

    expect(result.current.streamingMessages.get("agent-1")?.content).toBe(
      "可见回答",
    );

    act(() => {
      result.current.streamHandlers.onDelta?.(
        '`status_report\n{"state":"completed","rationale":"done"}\n```\n继续说明',
        {
          agent_id: "agent-1",
          agent_message_id: "message-1",
        },
      );
    });

    expect(result.current.streamingMessages.get("agent-1")?.content).toBe(
      "可见回答\n继续说明",
    );
  });
  it("keeps bare opening fences hidden until status_report body is removed", () => {
    const { result } = renderHook(() => useStreamingMessages("conversation-1"));

    act(() => {
      result.current.streamHandlers.onMessageStart({
        agent_id: "agent-1",
        agent_message_id: "message-1",
        agent_name: "Daily Chat Agent",
      });
    });

    act(() => {
      result.current.streamHandlers.onDelta?.("visible answer\n```\n", {
        agent_id: "agent-1",
        agent_message_id: "message-1",
      });
    });

    expect(result.current.streamingMessages.get("agent-1")?.content).toBe(
      "visible answer",
    );

    act(() => {
      result.current.streamHandlers.onDelta?.(
        'status_report\n{"state":"completed","will":"complete"}\n```\nfinal',
        {
          agent_id: "agent-1",
          agent_message_id: "message-1",
        },
      );
    });

    expect(result.current.streamingMessages.get("agent-1")?.content).toBe(
      "visible answer\nfinal",
    );
  });
});
