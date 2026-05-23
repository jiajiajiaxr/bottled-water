import type { ReactNode } from "react";
import { stripInternalAgentOutput } from "./message";

export function renderInlineMarkdown(text: string): ReactNode[] {
  const parts = text.split(/(`[^`]+`|\*\*[^*]+\*\*)/g).filter(Boolean);
  return parts.map((part, index) => {
    if (part.startsWith("`") && part.endsWith("`"))
      return <code key={index}>{part.slice(1, -1)}</code>;
    if (part.startsWith("**") && part.endsWith("**"))
      return <strong key={index}>{part.slice(2, -2)}</strong>;
    return <span key={index}>{part}</span>;
  });
}

export function MarkdownContent({ text }: { text: string }) {
  const blocks: ReactNode[] = [];
  const paragraph: string[] = [];
  const visibleText = stripInternalAgentOutput(text);
  const lines = visibleText.split(/\r?\n/);
  const flushParagraph = () => {
    if (!paragraph.length) return;
    blocks.push(
      <p key={`p-${blocks.length}`}>
        {renderInlineMarkdown(paragraph.join(" "))}
      </p>,
    );
    paragraph.length = 0;
  };
  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    if (line.trim().startsWith("```")) {
      flushParagraph();
      const code: string[] = [];
      index += 1;
      while (index < lines.length && !lines[index].trim().startsWith("```")) {
        code.push(lines[index]);
        index += 1;
      }
      blocks.push(
        <pre key={`code-${blocks.length}`}>
          <code>{code.join("\n")}</code>
        </pre>,
      );
      continue;
    }
    if (!line.trim()) {
      flushParagraph();
      continue;
    }
    const heading = /^(#{1,4})\s+(.+)$/.exec(line);
    if (heading) {
      flushParagraph();
      const level = Math.min(heading[1].length, 4);
      const content = renderInlineMarkdown(heading[2]);
      if (level === 1)
        blocks.push(<h3 key={`h-${blocks.length}`}>{content}</h3>);
      else if (level === 2)
        blocks.push(<h4 key={`h-${blocks.length}`}>{content}</h4>);
      else if (level === 3)
        blocks.push(<h5 key={`h-${blocks.length}`}>{content}</h5>);
      else blocks.push(<h6 key={`h-${blocks.length}`}>{content}</h6>);
      continue;
    }
    const listItems: string[] = [];
    if (/^\s*[-*]\s+/.test(line)) {
      flushParagraph();
      while (index < lines.length && /^\s*[-*]\s+/.test(lines[index])) {
        listItems.push(lines[index].replace(/^\s*[-*]\s+/, ""));
        index += 1;
      }
      index -= 1;
      blocks.push(
        <ul key={`ul-${blocks.length}`}>
          {listItems.map((item, itemIndex) => (
            <li key={itemIndex}>{renderInlineMarkdown(item)}</li>
          ))}
        </ul>,
      );
      continue;
    }
    if (/^\s*\d+[.)]\s+/.test(line)) {
      flushParagraph();
      while (index < lines.length && /^\s*\d+[.)]\s+/.test(lines[index])) {
        listItems.push(lines[index].replace(/^\s*\d+[.)]\s+/, ""));
        index += 1;
      }
      index -= 1;
      blocks.push(
        <ol key={`ol-${blocks.length}`}>
          {listItems.map((item, itemIndex) => (
            <li key={itemIndex}>{renderInlineMarkdown(item)}</li>
          ))}
        </ol>,
      );
      continue;
    }
    paragraph.push(line.trim());
  }
  flushParagraph();
  return (
    <div className="markdown-content">
      {blocks.length ? (
        blocks
      ) : (
        <p className="typing-placeholder">正在组织语言...</p>
      )}
    </div>
  );
}
