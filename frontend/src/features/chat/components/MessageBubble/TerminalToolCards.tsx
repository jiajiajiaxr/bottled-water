import { Space, Tag, Typography } from "antd";
import type { ChatMessage, ToolEventRecord } from "../../../../types";
import { toolEventsFromMessage } from "../../../../lib/toolEvents";

const { Text } = Typography;

interface TerminalToolCardsProps {
  message: ChatMessage;
}

export function TerminalToolCards({ message }: TerminalToolCardsProps) {
  const events = toolEventsFromMessage(message).filter((event) =>
    event.toolName.startsWith("terminal."),
  );
  if (!events.length) return null;
  return (
    <div className="message-terminal-cards">
      {events.map((event, index) => (
        <TerminalCard event={event} key={event.toolCallId || `${event.toolName}-${index}`} />
      ))}
    </div>
  );
}

function TerminalCard({ event }: { event: ToolEventRecord }) {
  const output = event.stdout || event.stderr || event.summary || "";
  return (
    <div className="message-terminal-card">
      <Space className="message-terminal-head" size={6} wrap>
        <Text strong>{event.toolName}</Text>
        {event.session_status && <Tag>{event.session_status}</Tag>}
        {event.status && <Tag color={event.status === "timeout" ? "orange" : "blue"}>{event.status}</Tag>}
        {event.exit_code !== undefined && <Tag>exit {event.exit_code}</Tag>}
      </Space>
      {event.command && <Text className="message-terminal-command">{event.command}</Text>}
      {output && <pre>{output}</pre>}
      {event.cwd && <Text type="secondary">{event.cwd}</Text>}
    </div>
  );
}
