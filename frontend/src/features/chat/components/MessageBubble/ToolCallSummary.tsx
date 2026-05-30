import { Tooltip, Typography } from "antd";
import type { ChatMessage } from "../../../../types";
import {
  summarizeToolEvents,
  toolEventDetailLines,
  toolEventsFromMessage,
} from "../../../../lib/toolEvents";

const { Text } = Typography;

interface ToolCallSummaryProps {
  message: ChatMessage;
}

export function ToolCallSummary({ message }: ToolCallSummaryProps) {
  const summary = summarizeToolEvents(toolEventsFromMessage(message));
  if (!summary) return null;
  return (
    <Tooltip
      title={
        <div className="tool-call-summary-popover">
          {summary.details.map((event, index) => (
            <div
              className="tool-call-summary-detail"
              key={event.toolCallId || `${event.toolName}-${index}`}
            >
              {toolEventDetailLines(event).map((line) => (
                <div key={line}>{line}</div>
              ))}
            </div>
          ))}
        </div>
      }
    >
      <Text
        className={`tool-call-summary ${summary.tone === "warning" ? "warning" : ""}`}
        data-testid="message-tool-summary"
      >
        {summary.label}
      </Text>
    </Tooltip>
  );
}
