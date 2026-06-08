import { MarkdownContent } from "@/lib";
import { BulbOutlined } from "@ant-design/icons";

interface ThinkingBlockProps {
  thinking: string;
  expanded: boolean;
  onExpandedChange: (expanded: boolean) => void;
}

export default function ThinkingBlock({
  thinking,
  expanded,
  onExpandedChange,
}: ThinkingBlockProps) {
  return (
    <div className="thinking-block">
      <button
        type="button"
        className="thinking-toggle"
        onClick={() => onExpandedChange(!expanded)}
      >
        <BulbOutlined />
        <span>思考过程</span>
        <span className="thinking-chevron">{expanded ? "▼" : "▶"}</span>
      </button>
      {expanded && (
        <div className="thinking-content">
          <MarkdownContent text={thinking} />
        </div>
      )}
    </div>
  );
}
