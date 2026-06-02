import React, { useMemo, type ReactNode } from "react";
import { stripInternalAgentOutput } from "./message";
import { renderInlineMarkdown } from "./markdown-inline";

export interface MarkdownCodeBlock {
  index: number;
  language: string;
  code: string;
}

export interface MarkdownCodeRunResult {
  status?: string;
  stdout?: string;
  stderr?: string;
  exit_code?: number | null;
  duration_ms?: number | null;
  error?: string;
}

interface MarkdownContentProps {
  text: string;
  codeBlockResults?: Record<number, MarkdownCodeRunResult>;
  codeBlockRunning?: Record<number, boolean>;
  onRunCodeBlock?: (block: MarkdownCodeBlock) => void;
}

function CodeRunResultView({ result }: { result?: MarkdownCodeRunResult }) {
  if (!result) return null;
  const status = result.status ?? (result.error ? "failed" : "completed");
  return (
    <div className={`markdown-code-run-result ${status === "succeeded" ? "succeeded" : "failed"}`}>
      <div className="markdown-code-run-meta">
        <span>状态：{status}</span>
        {typeof result.exit_code !== "undefined" && (
          <span>exit_code：{String(result.exit_code)}</span>
        )}
        {typeof result.duration_ms === "number" && (
          <span>耗时：{result.duration_ms} ms</span>
        )}
      </div>
      {result.stdout && (
        <pre className="markdown-code-run-output">
          <code>{result.stdout}</code>
        </pre>
      )}
      {(result.stderr || result.error) && (
        <pre className="markdown-code-run-output error">
          <code>{result.stderr || result.error}</code>
        </pre>
      )}
    </div>
  );
}

function MarkdownContentComponent({
  text,
  codeBlockResults,
  codeBlockRunning,
  onRunCodeBlock,
}: MarkdownContentProps) {
  const blocks = useMemo(() => {
    const result: ReactNode[] = [];
    const paragraph: string[] = [];
    const visibleText = stripInternalAgentOutput(text);
    const lines = visibleText.split(/\r?\n/);
    let codeBlockIndex = 0;
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
        const language = line.trim().replace(/^```/, "").trim().toLowerCase();
        const code: string[] = [];
        index += 1;
        while (index < lines.length && !lines[index].trim().startsWith("```")) {
          code.push(lines[index]);
          index += 1;
        }
        const blockIndex = codeBlockIndex;
        codeBlockIndex += 1;
        const codeText = code.join("\n");
        const runnable = ["python", "py"].includes(language) && onRunCodeBlock;
        const running = Boolean(codeBlockRunning?.[blockIndex]);
        result.push(
          <div className="markdown-code-block" key={`code-${result.length}`}>
            {(language || runnable) && (
              <div className="markdown-code-toolbar">
                <span>{language || "code"}</span>
                {runnable && (
                  <button
                    type="button"
                    className="markdown-code-run-button"
                    disabled={running}
                    onClick={() =>
                      onRunCodeBlock({
                        index: blockIndex,
                        language: language || "python",
                        code: codeText,
                      })
                    }
                  >
                    {running ? "运行中..." : "运行"}
                  </button>
                )}
              </div>
            )}
            <pre>
              <code>{codeText}</code>
            </pre>
            <CodeRunResultView result={codeBlockResults?.[blockIndex]} />
          </div>,
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
  }, [codeBlockResults, codeBlockRunning, onRunCodeBlock, text]);

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
