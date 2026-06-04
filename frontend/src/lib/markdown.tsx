import React, { useMemo, type ReactNode } from "react";
import { stripInternalAgentOutput } from "./message";
import { renderInlineMarkdown } from "./markdown-inline";

function MarkdownContentComponent({ text }: { text: string }) {
  const blocks = useMemo(() => {
    const result: ReactNode[] = [];
    const paragraph: string[] = [];
    const visibleText = stripInternalAgentOutput(text);
    const lines = visibleText.split(/\r?\n/);
    const flushParagraph = () => {
      if (!paragraph.length) return;
      result.push(
        <p key={`p-${result.length}`}>
          {renderInlineMarkdown(paragraph.join(" "))}
        </p>,
      );
      paragraph.length = 0;
    };
    for (let index = 0; index < lines.length; index += 1) {
      const line = lines[index];
      if (line.trim().startsWith("```")) {
        flushParagraph();
        const fenceName = line
          .trim()
          .replace(/^```\s*/, "")
          .split(/\s+/)[0]
          ?.toLowerCase();
        const isInternalFence =
          fenceName === "status_report" || fenceName === "status";
        const code: string[] = [];
        index += 1;
        while (index < lines.length && !lines[index].trim().startsWith("```")) {
          code.push(lines[index]);
          index += 1;
        }
        if (isInternalFence) continue;
        result.push(
          <pre key={`code-${result.length}`}>
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
          result.push(<h3 key={`h-${result.length}`}>{content}</h3>);
        else if (level === 2)
          result.push(<h4 key={`h-${result.length}`}>{content}</h4>);
        else if (level === 3)
          result.push(<h5 key={`h-${result.length}`}>{content}</h5>);
        else result.push(<h6 key={`h-${result.length}`}>{content}</h6>);
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
        result.push(
          <ul key={`ul-${result.length}`}>
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
        result.push(
          <ol key={`ol-${result.length}`}>
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
    return result;
  }, [text]);

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

export const MarkdownContent = React.memo(MarkdownContentComponent);
